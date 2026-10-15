import os
import sys
import time
import socket
import shutil
import logging
import asyncio
import subprocess
from typing import Optional, List
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_URL = f"http://127.0.0.1:{DEFAULT_CDP_PORT}"

logger = logging.getLogger("BrowserManager")


def find_chrome_executable() -> Optional[str]:
    """
    Finds the Google Chrome or Chromium executable across Linux, Windows, and macOS.
    """
    # 1. Check explicit environment override
    custom_bin = os.environ.get("CHROME_BIN")
    if custom_bin and os.path.isfile(custom_bin):
        return custom_bin

    # 2. Linux binaries & package paths
    if sys.platform.startswith("linux"):
        linux_candidates = [
            "google-chrome-stable",
            "google-chrome",
            "chromium-browser",
            "chromium",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "/var/lib/flatpak/exports/bin/com.google.Chrome"
        ]
        for candidate in linux_candidates:
            found = shutil.which(candidate) or (os.path.isfile(candidate) and candidate)
            if found:
                return str(found)

    # 3. Windows standard installation paths
    elif sys.platform == "win32":
        win_candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for candidate in win_candidates:
            if os.path.isfile(candidate):
                return candidate
        found = shutil.which("chrome") or shutil.which("chrome.exe")
        if found:
            return str(found)

    # 4. macOS applications
    elif sys.platform == "darwin":
        mac_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"
        ]
        for candidate in mac_candidates:
            if os.path.isfile(candidate):
                return candidate

    return None


def is_port_open(host: str = "127.0.0.1", port: int = DEFAULT_CDP_PORT) -> bool:
    """
    Checks if the CDP port is actively listening.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.6)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_default_profile_dir() -> str:
    """
    Returns an appropriate persistent user data directory across Linux, Windows, and macOS.
    """
    if sys.platform.startswith("linux"):
        config_dir = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        profile_dir = os.path.join(config_dir, "gemini-chrome-profile")
    elif sys.platform == "darwin":
        profile_dir = os.path.expanduser("~/Library/Application Support/gemini-chrome-profile")
    else:
        profile_dir = os.path.abspath("./chrome-dev-profile")

    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


def launch_chrome_process(
    port: int = DEFAULT_CDP_PORT,
    headless: Optional[bool] = None,
    profile_dir: Optional[str] = None
) -> subprocess.Popen:
    """
    Spawns Google Chrome/Chromium with remote debugging enabled.
    Optimized for Linux (including Docker/headless servers) and Windows.
    """
    chrome_bin = find_chrome_executable()
    if not chrome_bin:
        err_msg = (
            "Google Chrome or Chromium was not found on this system.\n"
            "On Linux, install it via:\n"
            "  sudo apt update && sudo apt install -y google-chrome-stable  # or chromium-browser\n"
            "Or set the CHROME_BIN environment variable to your browser binary path."
        )
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    if not profile_dir:
        profile_dir = get_default_profile_dir()

    # Automatically detect headless mode on Linux if no display server is present
    if headless is None:
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            logger.info("No DISPLAY / WAYLAND_DISPLAY detected on Linux. Enabling headless mode automatically.")
            headless = True
        else:
            headless = False

    args = [
        chrome_bin,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled"
    ]

    # Linux & Docker optimizations
    if sys.platform.startswith("linux"):
        args.extend([
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox"
        ])

    if headless:
        args.extend([
            "--headless=new",
            "--disable-gpu",
            "--disable-software-rasterizer"
        ])

    args.append("https://gemini.google.com")

    logger.info(f"Auto-launching browser: {chrome_bin}")
    logger.info(f"User profile: {profile_dir} | Headless: {headless} | Port: {port}")

    popen_kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }

    if sys.platform != "win32":
        # Detach cleanly on Linux/macOS
        popen_kwargs["start_new_session"] = True
    else:
        # Detached process on Windows
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        popen_kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(args, **popen_kwargs)

    # Wait until CDP port becomes responsive
    max_wait_seconds = 20
    start_time = time.time()
    while (time.time() - start_time) < max_wait_seconds:
        if is_port_open(port=port):
            logger.info(f"[✓] Browser is listening on 127.0.0.1:{port}")
            return proc
        time.sleep(0.5)

    logger.warning(f"Browser launched, but port {port} did not respond within {max_wait_seconds}s. Proceeding to attempt connection...")
    return proc


class BrowserManager:
    """
    Manages asynchronous Playwright CDP connection to Google Chrome/Chromium
    with automatic browser discovery and launch on Linux, Windows, and macOS.
    """

    def __init__(self, cdp_url: str = DEFAULT_CDP_URL, port: int = DEFAULT_CDP_PORT, auto_launch: bool = True, headless: Optional[bool] = None):
        self.port = port
        self.cdp_url = cdp_url or f"http://127.0.0.1:{port}"
        self.auto_launch = auto_launch
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> BrowserContext:
        """
        Connects or reconnects to the running Chrome instance via CDP.
        If port is not active and auto_launch is True, automatically starts Chrome.
        """
        async with self._lock:
            if self._context and self._browser and self._browser.is_connected():
                return self._context

            # Check if port is open; if not, automatically launch browser
            if not is_port_open(port=self.port):
                if self.auto_launch:
                    logger.info(f"Chrome is not running on port {self.port}. Starting browser automatically...")
                    launch_chrome_process(port=self.port, headless=self.headless)
                    await asyncio.sleep(1.0)
                else:
                    raise ConnectionError(
                        f"Port {self.port} is closed and auto_launch is disabled. "
                        "Please start Google Chrome with --remote-debugging-port=9222"
                    )

            if not self._playwright:
                self._playwright = await async_playwright().start()

            for attempt in range(1, 4):
                try:
                    self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
                    contexts = self._browser.contexts
                    if contexts:
                        self._context = contexts[0]
                    else:
                        self._context = await self._browser.new_context()

                    logger.info(f"[✓] Connected to Chrome CDP at {self.cdp_url}")
                    return self._context
                except Exception as e:
                    logger.warning(f"Connection attempt {attempt}/3 failed ({e}). Retrying...")
                    await asyncio.sleep(1.5)

            raise ConnectionError(
                f"Could not connect to Chrome CDP at {self.cdp_url} after multiple attempts. "
                "Ensure Chrome is running and port 9222 is accessible."
            )

    async def get_context(self) -> BrowserContext:
        """
        Retrieves the active browser context, establishing connection if necessary.
        """
        if not self._context or not self._browser or not self._browser.is_connected():
            return await self.connect()
        return self._context

    async def open_worker_tab(self) -> Page:
        """
        Opens a dedicated, isolated browser tab (Page).
        """
        context = await self.get_context()
        page = await context.new_page()
        page.set_default_timeout(60000)
        return page

    async def close_tab(self, page: Optional[Page]):
        """
        Safely closes a worker tab without impacting other concurrent tabs.
        """
        if page:
            try:
                if not page.is_closed():
                    await page.close()
            except Exception as e:
                logger.warning(f"Error while closing tab: {e}")

    async def close(self):
        """
        Gracefully disconnects from browser and stops Playwright.
        """
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
                self._context = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None


# Global singleton instance
browser_manager = BrowserManager()
