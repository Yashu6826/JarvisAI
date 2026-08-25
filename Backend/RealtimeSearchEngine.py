import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from Backend.LLMProvider import (
    LMSTUDIO_MODEL,
    LocalLLMUnavailable,
    generate_text,
    get_config,
)


SERPER_SEARCH_URL = "https://google.serper.dev/search"
SEARCH_LIMIT_MAX = 10
_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "can", "for",
    "from", "how", "i", "in", "is", "it", "latest", "me", "of", "on",
    "or", "search", "show", "tell", "that", "the", "this", "to", "what",
    "where", "which", "with", "you",
}
_ADULT_RESULT_PATTERN = re.compile(
    r"(?:^|[.\s/_-])(?:porn|porno|pornhub|xxx|xvideos|xnxx|xhamster|redtube|"
    r"youporn|brazzers|onlyfans|hentai|escort|adult[-_ ]?video)(?:$|[.\s/_-])",
    re.I,
)
_ADULT_QUERY_PATTERN = re.compile(
    r"\b(?:adult content|porn|pornography|xxx|hentai|sex video|escort)\b",
    re.I,
)
_LOW_VALUE_RESULT_PATTERN = re.compile(
    r"\b(?:dictionary|definition|meaning|thesaurus)\b",
    re.I,
)
_DEFINITION_QUERY_PATTERN = re.compile(
    r"\b(?:define|definition|meaning|what does .* mean)\b",
    re.I,
)


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


def _canonical_result_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, "", parsed.query, ""))


def _query_terms(prompt: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", prompt.lower())
        if len(token) > 1 and token not in _SEARCH_STOPWORDS
    }


def _result_is_safe(result: dict[str, str], prompt: str) -> bool:
    if _ADULT_QUERY_PATTERN.search(prompt):
        return True
    haystack = " ".join(
        str(result.get(key) or "")
        for key in ("title", "url", "snippet")
    )
    if _ADULT_RESULT_PATTERN.search(haystack):
        return False
    if not _DEFINITION_QUERY_PATTERN.search(prompt) and _LOW_VALUE_RESULT_PATTERN.search(haystack):
        return False
    return True


def _rank_relevant_results(
    prompt: str,
    results: list[dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    """Reject unsafe/off-topic provider noise and return stable relevance order."""
    terms = _query_terms(prompt)
    minimum_overlap = 2 if len(terms) >= 5 else 1
    ranked: list[tuple[float, int, dict[str, str]]] = []
    seen: set[str] = set()
    normalized_prompt = " ".join(prompt.lower().split())

    for provider_rank, result in enumerate(results):
        url = str(result.get("url") or "").strip()
        canonical = _canonical_result_url(url)
        title = _clean(str(result.get("title") or ""))
        snippet = _clean(str(result.get("snippet") or ""))
        if not canonical or canonical in seen or not title:
            continue
        candidate = {
            "title": title,
            "url": url,
            "site_root": _site_root(url),
            "snippet": snippet,
        }
        provider = str(result.get("provider") or "").strip()
        if provider:
            candidate["provider"] = provider
        if not _result_is_safe(candidate, prompt):
            continue

        parsed = urlparse(url)
        title_terms = set(re.findall(r"[a-z0-9]+", title.lower()))
        body_terms = set(re.findall(
            r"[a-z0-9]+",
            f"{title} {snippet} {parsed.netloc}".lower(),
        ))
        title_overlap = len(terms & title_terms)
        total_overlap = len(terms & body_terms)
        if terms and total_overlap < minimum_overlap:
            continue
        exact_bonus = 2.5 if normalized_prompt in f"{title} {snippet}".lower() else 0.0
        score = (title_overlap * 3.0) + total_overlap + exact_bonus
        ranked.append((score, provider_rank, candidate))
        seen.add(canonical)

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _search_timeout() -> float:
    try:
        return max(2.0, min(float(get_config("WEB_SEARCH_TIMEOUT_SECONDS", "15")), 30.0))
    except (TypeError, ValueError):
        return 15.0


def _serper_results(prompt: str, limit: int) -> list[dict[str, str]]:
    """Use Serper when configured; an absent key is a normal fallback state."""
    api_key = get_config("SERPER_API_KEY", "").strip()
    if not api_key:
        return []
    payload: dict[str, object] = {"q": prompt, "num": limit}
    country = get_config("SERPER_COUNTRY_CODE", "").strip().lower()
    language = get_config("SERPER_LANGUAGE_CODE", "").strip().lower()
    if country:
        payload["gl"] = country
    if language:
        payload["hl"] = language
    response = requests.post(
        SERPER_SEARCH_URL,
        json=payload,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        timeout=_search_timeout(),
    )
    response.raise_for_status()
    try:
        data = response.json()
    except (TypeError, ValueError):
        return []
    organic = data.get("organic", []) if isinstance(data, dict) else []
    if not isinstance(organic, list):
        return []
    results: list[dict[str, str]] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        direct_url = str(item.get("link") or "").strip()
        if not _site_root(direct_url):
            continue
        date = _clean(str(item.get("date") or ""))
        snippet = _clean(str(item.get("snippet") or ""))
        if date:
            snippet = f"{snippet} ({date})" if snippet else date
        results.append({
            "title": _clean(str(item.get("title") or "")),
            "url": direct_url,
            "site_root": _site_root(direct_url),
            "snippet": snippet,
            "provider": "serper",
        })
        if len(results) >= limit:
            break
    return results


def _duckduckgo_results(prompt: str, limit: int) -> list[dict[str, str]]:
    response = requests.get(
        f"https://html.duckduckgo.com/html/?q={quote_plus(prompt)}",
        headers={"User-Agent": "Mozilla/5.0 NexaDesktopAssistant/2.0"},
        timeout=_search_timeout(),
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
            "provider": "duckduckgo",
        })
        if len(results) >= limit:
            break
    return results


def _bing_rss_results(prompt: str, limit: int) -> list[dict[str, str]]:
    response = requests.get(
        "https://www.bing.com/search",
        params={"q": prompt, "format": "rss"},
        headers={"User-Agent": "Mozilla/5.0 NexaDesktopAssistant/2.0"},
        timeout=_search_timeout(),
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
            "provider": "bing",
        })
        if len(results) >= limit:
            break
    return results


def SearchWeb(prompt: str, limit: int = 6) -> list[dict[str, str]]:
    """Search Serper first when configured, then use two no-key fallbacks."""
    cleaned_prompt = " ".join(str(prompt or "").split())
    if not cleaned_prompt:
        return []
    bounded_limit = max(1, min(limit, SEARCH_LIMIT_MAX))
    last_error: requests.RequestException | None = None
    for provider in (_serper_results, _duckduckgo_results, _bing_rss_results):
        try:
            candidates = provider(cleaned_prompt, bounded_limit)
        except requests.RequestException as exc:
            last_error = exc
            continue
        results = _rank_relevant_results(cleaned_prompt, candidates, bounded_limit)
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
