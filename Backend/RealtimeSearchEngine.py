import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from Backend.LLMProvider import LMSTUDIO_MODEL, LocalLLMUnavailable, generate_text


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _direct_result_url(value: str) -> str:
    """Turn DuckDuckGo redirect links into URLs an agent can safely inspect."""
    decoded = html.unescape(value)
    if decoded.startswith("//"):
        decoded = f"https:{decoded}"
    parsed = urlparse(decoded)
    redirected = parse_qs(parsed.query).get("uddg", [])
    return unquote(redirected[0]) if redirected else decoded


def _site_root(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _duckduckgo_results(prompt: str, limit: int) -> list[dict[str, str]]:
    response = requests.get(
        f"https://html.duckduckgo.com/html/?q={quote_plus(prompt)}",
        headers={"User-Agent": "Mozilla/5.0 NexaDesktopAssistant/2.0"},
        timeout=15,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []
    for result in soup.select(".result"):
        link = result.select_one(".result__a")
        if not link:
            continue
        direct_url = _direct_result_url(str(link.get("href") or ""))
        snippet = result.select_one(".result__snippet")
        if not _site_root(direct_url):
            continue
        results.append({
            "title": _clean(link.get_text(" ", strip=True)),
            "url": direct_url,
            "site_root": _site_root(direct_url),
            "snippet": _clean(snippet.get_text(" ", strip=True)) if snippet else "",
        })
        if len(results) >= limit:
            break
    return results


def _bing_rss_results(prompt: str, limit: int) -> list[dict[str, str]]:
    response = requests.get(
        "https://www.bing.com/search",
        params={"q": prompt, "format": "rss"},
        headers={"User-Agent": "Mozilla/5.0 NexaDesktopAssistant/2.0"},
        timeout=15,
    )
    response.raise_for_status()
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return []
    results: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        direct_url = str(item.findtext("link") or "").strip()
        if not _site_root(direct_url):
            continue
        results.append({
            "title": _clean(str(item.findtext("title") or "")),
            "url": direct_url,
            "site_root": _site_root(direct_url),
            "snippet": _clean(str(item.findtext("description") or "")),
        })
        if len(results) >= limit:
            break
    return results


def SearchWeb(prompt: str, limit: int = 6) -> list[dict[str, str]]:
    """Fetch public results with a second provider when the first is unavailable."""
    last_error: requests.RequestException | None = None
    for provider in (_duckduckgo_results, _bing_rss_results):
        try:
            results = provider(prompt, max(1, min(limit, 10)))
        except requests.RequestException as exc:
            last_error = exc
            continue
        if results:
            return results
    if last_error:
        raise last_error
    return []


def RealtimeSearchEngine(prompt: str) -> str:
    try:
        results = SearchWeb(prompt)
    except requests.RequestException:
        return "I could not reach the web search service. Check your internet connection and try again."
    if not results:
        return "I searched the web but could not find a reliable result for that request."

    evidence = "\n".join(
        f"[{index}] {item['title']}\n{item['snippet']}\nURL: {item['url']}"
        for index, item in enumerate(results, 1)
    )
    try:
        return generate_text(
            prompt=f"User request: {prompt}\n\nLive search results:\n{evidence}",
            system=(
                "Answer using only the supplied live search results. Be concise. "
                "For changing numbers such as prices, clearly say the value and that "
                "it may move. Cite supporting result numbers like [1]. Never invent "
                "missing facts. End with a short Sources list containing the URLs used."
            ),
            model=LMSTUDIO_MODEL,
            temperature=0.2,
            reasoning="off",
        )
    except LocalLLMUnavailable as exc:
        return str(exc)


if __name__ == "__main__":
    print(RealtimeSearchEngine("latest news"))
