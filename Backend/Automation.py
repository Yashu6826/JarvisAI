import asyncio
import logging
import platform
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from Backend.LLMProvider import LMSTUDIO_MODEL, LocalLLMUnavailable, generate_text

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent / "Data"
DATA_DIR.mkdir(exist_ok=True)


def _clean_open_target(target: str) -> str:
    cleaned = " ".join(target.strip().rstrip(".,!?").lower().split())
    cleaned = re.sub(r"^(?:the|official)\s+", "", cleaned)
    cleaned = re.sub(r"\s+(?:official\s+)?(?:website|web site|site|page|app)$", "", cleaned)
    return cleaned.strip()


def _website_url(target: str) -> str | None:
    cleaned = target.strip().rstrip(".,!?")
    lowered = _clean_open_target(cleaned)
    if lowered.startswith(("http://", "https://")):
        parsed = urlparse(cleaned)
        return cleaned if parsed.netloc else None
    if re.fullmatch(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/.*)?", lowered):
        return f"https://{cleaned}"
    return None


def _official_site_search_url(target: str) -> str:
    cleaned = _clean_open_target(target) or target.strip()
    return f"https://www.google.com/search?q={quote_plus(cleaned + ' official website')}&btnI=1"


def OpenLocalApp(app_name: str) -> bool:
    """Open only an installed application; never guess a website."""
    try:
        from AppOpener import open as appopen

        appopen(app_name, match_closest=True, output=True, throw_error=True)
        logger.info("Opened local application '%s'.", app_name)
        return True
    except Exception as exc:
        logger.warning("Could not open local application '%s': %s", app_name, exc)
        return False


def OpenApp(app_name: str) -> bool:
    """Legacy helper for the desktop UI; the LangGraph agent uses separate tools."""
    website = _website_url(app_name)
    if website:
        opened = webbrowser.open(website, new=2)
        logger.info("Opened website '%s'.", website)
        return bool(opened)

    if OpenLocalApp(app_name):
        return True

    fallback = _official_site_search_url(app_name)
    opened = webbrowser.open(fallback, new=2)
    logger.info("Opened official-site search fallback '%s'.", fallback)
    return bool(opened)


def OpenWebSearch(query: str) -> bool:
    return bool(webbrowser.open(
        f"https://www.google.com/search?q={quote_plus(query.strip())}",
        new=2,
    ))


def CloseApp(app_name: str) -> bool:
    if "chrome" in app_name.lower():
        return False
    try:
        from AppOpener import close

        close(app_name, match_closest=True, output=True, throw_error=True)
        return True
    except Exception:
        return False


def _safe_file_name(topic: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.strip()).strip("_")
    return safe_name[:80] or "document"


def Content(topic: str) -> bool:
    try:
        answer = generate_text(
            prompt=topic,
            system=(
                "You are a helpful local content writer. Write clear, polished "
                "content for the user's request. Return only the requested content."
            ),
            model=LMSTUDIO_MODEL,
            temperature=0.7,
        )
    except LocalLLMUnavailable as exc:
        logger.error("Content generation unavailable: %s", exc)
        return False

    output_path = DATA_DIR / f"{_safe_file_name(topic)}.txt"
    output_path.write_text(answer, encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(output_path)])
    return True


def System(command: str) -> bool:
    import keyboard

    actions = {
        "mute": "volume mute",
        "unmute": "volume unmute",
        "volume up": "volume up",
        "volume down": "volume down",
    }
    key = actions.get(command.lower())
    if not key:
        return False
    keyboard.press_and_release(key)
    return True


def SetBrightness(level: int) -> bool:
    """Set display brightness on Windows using WMI."""
    safe_level = max(0, min(100, int(level)))
    script = (
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        f".WmiSetBrightness(1,{safe_level})"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def ChangeBrightness(direction: str, step: int = 10) -> bool:
    """Increase or decrease brightness in bounded steps."""
    safe_step = max(1, min(100, int(step)))
    get_script = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", get_script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return False
        current = int((result.stdout or "").strip().splitlines()[-1])
    except Exception:
        return False

    if direction == "up":
        target = current + safe_step
    elif direction == "down":
        target = current - safe_step
    else:
        return False
    return SetBrightness(target)


def GetSystemSpecs() -> dict[str, str]:
    """Collect a concise set of Windows system specifications."""
    specs = {
        "device_name": platform.node() or "Unknown",
        "os": f"{platform.system()} {platform.release()}",
        "version": platform.version(),
        "architecture": platform.machine() or "Unknown",
        "processor": platform.processor() or "Unknown",
        "ram": "Unknown",
        "storage": "Unknown",
        "gpu": "Unknown",
    }

    commands = {
        "ram": [
            "powershell",
            "-NoProfile",
            "-Command",
            "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)",
        ],
        "storage": [
            "powershell",
            "-NoProfile",
            "-Command",
            "[math]::Round((Get-CimInstance Win32_LogicalDisk -Filter \"DriveType=3\" | Measure-Object -Property Size -Sum).Sum / 1GB, 2)",
        ],
        "gpu": [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)",
        ],
    }

    for key, command in commands.items():
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if result.returncode == 0:
                value = (result.stdout or "").strip().splitlines()
                if value:
                    specs[key] = value[-1].strip()
        except Exception:
            continue

    if specs["ram"] != "Unknown":
        specs["ram"] = f'{specs["ram"]} GB'
    if specs["storage"] != "Unknown":
        specs["storage"] = f'{specs["storage"]} GB'
    return specs


def GetPowerAndWifiStatus() -> dict[str, str]:
    """Read battery percentage/charging state and Wi-Fi connection status."""
    status = {
        "battery_percentage": "Unknown",
        "battery_state": "Unknown",
        "wifi_status": "Unknown",
        "wifi_name": "",
    }

    battery_script = (
        "$b = Get-CimInstance Win32_Battery | Select-Object -First 1;"
        "if ($null -eq $b) { 'Unavailable|Desktop or battery not detected' } "
        "else { \"$($b.EstimatedChargeRemaining)|$($b.BatteryStatus)\" }"
    )
    wifi_script = (
        "$profile = netsh wlan show interfaces | Select-String '^\\s*SSID\\s*:\\s*(.+)$' | "
        "Select-Object -First 1;"
        "$state = netsh wlan show interfaces | Select-String '^\\s*State\\s*:\\s*(.+)$' | "
        "Select-Object -First 1;"
        "if ($null -eq $state) { 'Unknown|' } "
        "else { "
        "$wifiState = ($state.Matches[0].Groups[1].Value).Trim();"
        "$wifiName = if ($profile) { ($profile.Matches[0].Groups[1].Value).Trim() } else { '' };"
        "\"$wifiState|$wifiName\" }"
    )

    try:
        battery_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", battery_script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if battery_result.returncode == 0:
            battery_value = (battery_result.stdout or "").strip().split("|", 1)
            if len(battery_value) == 2:
                status["battery_percentage"] = battery_value[0].strip() or "Unknown"
                battery_state_code = battery_value[1].strip()
                battery_states = {
                    "1": "Discharging",
                    "2": "AC connected",
                    "3": "Fully charged",
                    "4": "Low",
                    "5": "Critical",
                    "6": "Charging",
                    "7": "Charging and high",
                    "8": "Charging and low",
                    "9": "Charging and critical",
                    "10": "Undefined",
                    "11": "Partially charged",
                    "Desktop or battery not detected": "Desktop or battery not detected",
                }
                status["battery_state"] = battery_states.get(battery_state_code, battery_state_code or "Unknown")
    except Exception:
        pass

    try:
        wifi_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", wifi_script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if wifi_result.returncode == 0:
            wifi_value = (wifi_result.stdout or "").strip().split("|", 1)
            if len(wifi_value) == 2:
                status["wifi_status"] = wifi_value[0].strip() or "Unknown"
                status["wifi_name"] = wifi_value[1].strip()
    except Exception:
        pass

    if status["battery_percentage"] not in {"Unknown", "Unavailable"} and status["battery_percentage"].isdigit():
        status["battery_percentage"] = f'{status["battery_percentage"]}%'
    return status


async def TranslateAndExecute(commands: list[str]):
    tasks = []
    for command in commands:
        if command.startswith("open "):
            tasks.append(asyncio.to_thread(OpenApp, command.removeprefix("open ")))
        elif command.startswith("close "):
            tasks.append(asyncio.to_thread(CloseApp, command.removeprefix("close ")))
        elif command.startswith("content "):
            tasks.append(asyncio.to_thread(Content, command.removeprefix("content ")))
        elif command.startswith("system "):
            tasks.append(asyncio.to_thread(System, command.removeprefix("system ")))

    for result in await asyncio.gather(*tasks):
        yield result


async def Automation(commands: list[str]) -> bool:
    results = []
    async for result in TranslateAndExecute(commands):
        results.append(bool(result))
    return bool(results) and all(results)


if __name__ == "__main__":
    asyncio.run(Automation(["content a short leave application"]))
