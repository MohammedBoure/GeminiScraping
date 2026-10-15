import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

DEFAULT_CDP_URL = "http://127.0.0.1:9222"

logger = logging.getLogger("BrowserManager")


class BrowserManager:
    """
    Manages asynchronous Playwright CDP connection to an active Chrome browser session
    and coordinates isolated tab lifecycles.
    """

    def __init__(self, cdp_url: str = DEFAULT_CDP_URL):
        self.cdp_url = cdp_url
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> BrowserContext:
        """
        Connects or reconnects to the running Chrome instance via CDP.
        """
        async with self._lock:
            if self._context and self._browser and self._browser.is_connected():
                return self._context

            if not self._playwright:
                self._playwright = await async_playwright().start()

            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
                contexts = self._browser.contexts
                if contexts:
                    self._context = contexts[0]
                else:
                    self._context = await self._browser.new_context()

                logger.info(f"Connected to Chrome CDP at {self.cdp_url}")
                return self._context
            except Exception as e:
                logger.error(f"Failed to connect to Chrome at {self.cdp_url}: {e}")
                raise ConnectionError(
                    f"Could not connect to Chrome CDP at {self.cdp_url}. "
                    "Ensure Google Chrome is running with --remote-debugging-port=9222"
                ) from e

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
        # Set generous default timeout for video generation actions
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


# Global singleton instance for easy import across modules
browser_manager = BrowserManager()
