import os
import re
import time
import base64
import logging
import asyncio
from typing import Optional
import aiohttp
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("GeminiPage")

INPUT_SELECTOR = "div.ql-editor.textarea, rich-textarea p, div[contenteditable='true'], textarea"
SEND_BUTTON_SELECTOR = "button[aria-label*='Send'], button[aria-label*='إرسال'], button.send-button, button.mat-mdc-unelevated-button"
DOWNLOAD_BUTTON_SELECTOR = (
    "button[aria-label*='Download'], button[aria-label*='تحميل'], "
    "a[download], button[data-test-id*='download'], "
    "button[aria-label*='Download video'], button[aria-label*='تنزيل الفيديو']"
)
ERROR_SELECTORS = [
    "div.error-message",
    "div[role='alert']",
    "message-content:has-text('cannot generate')",
    "message-content:has-text('I can\\'t generate')",
    "message-content:has-text('لا أستطيع إنشاء')",
    "message-content:has-text('حدث خطأ')",
    "message-content:has-text('Error 1095')"
]


async def ensure_video_mode(page: Page):
    """
    Checks for tools/extensions menu to select video mode if explicitly required by UI.
    """
    try:
        tool_btn = page.locator("button[aria-label*='Tools'], button[aria-label*='أدوات'], button:has-text('Tools')").first
        if await tool_btn.count() > 0 and await tool_btn.is_visible():
            await tool_btn.click()
            await asyncio.sleep(0.5)
            video_opt = page.locator("text=/Video|فيديو|Generate video/i").first
            if await video_opt.count() > 0 and await video_opt.is_visible():
                await video_opt.click()
                logger.info("Video generation tool mode selected.")
    except Exception as e:
        logger.debug(f"Video mode check skipped or not needed: {e}")


async def init_gemini_page(page: Page):
    """
    Navigates to Gemini, ensures video mode if required, and waits for editor.
    """
    logger.info("Navigating to https://gemini.google.com ...")
    try:
        await page.goto("https://gemini.google.com", wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        logger.warning(f"Initial navigation warning: {e}. Checking if page loaded anyway...")

    # Wait for the input container to appear
    try:
        await page.locator(INPUT_SELECTOR).first.wait_for(state="visible", timeout=30000)
        logger.info("Gemini editor interface detected and ready.")
        await ensure_video_mode(page)
    except Exception as e:
        logger.error("Failed to find Gemini editor prompt container. Ensure you are logged into Google Gemini.")
        raise RuntimeError("Gemini input editor not found. Make sure user is logged in.") from e


async def inject_prompt(page: Page, prompt: str):
    """
    Injects prompt text directly into the DOM using JavaScript evaluation
    to prevent quoting or shell escaping issues with Arabic and multi-line strings.
    """
    logger.info(f"Injecting prompt: {prompt[:80]}...")
    await page.evaluate("""
        (text) => {
            const el = document.querySelector('div.ql-editor.textarea') || 
                       document.querySelector('rich-textarea p') || 
                       document.querySelector('div[contenteditable="true"]') ||
                       document.querySelector('textarea');
            if (el) {
                el.focus();
                el.innerText = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    """, prompt)
    await asyncio.sleep(0.8)


async def submit_prompt(page: Page):
    """
    Triggers submission via the Send button if visible and enabled, or falls back to Enter.
    """
    send_btn = page.locator(SEND_BUTTON_SELECTOR).last
    try:
        if await send_btn.is_visible() and await send_btn.is_enabled():
            await send_btn.click()
            logger.info("Prompt submitted via Send button.")
        else:
            await page.keyboard.press("Enter")
            logger.info("Prompt submitted via Enter key.")
    except Exception as e:
        logger.warning(f"Send button click failed ({e}), falling back to Enter key.")
        await page.keyboard.press("Enter")


async def download_file_from_url(url: str, output_path: str):
    """
    Downloads media file via direct HTTP/HTTPS streaming using aiohttp.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status == 200:
                with open(output_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024 * 64)
                        if not chunk:
                            break
                        f.write(chunk)
                logger.info(f"Direct media URL downloaded to {output_path}")
            else:
                raise RuntimeError(f"HTTP request failed with status {resp.status} for URL: {url}")


async def extract_blob_video(page: Page, blob_url: str, output_path: str):
    """
    Extracts video bytes from an in-page blob: URL by encoding it as base64 inside the page,
    then decoding and writing it to disk.
    """
    logger.info(f"Extracting blob video stream from {blob_url}...")
    base64_data = await page.evaluate("""
        async (blobUrl) => {
            const response = await fetch(blobUrl);
            const blob = await response.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }
    """, blob_url)

    if not base64_data or not isinstance(base64_data, str):
        raise ValueError("Failed to extract base64 data from blob URL.")

    # Strip the Data-URL header if present (e.g. 'data:video/mp4;base64,')
    if "," in base64_data:
        _, base64_data = base64_data.split(",", 1)

    video_bytes = base64.b64decode(base64_data)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(video_bytes)

    file_size = os.path.getsize(output_path)
    logger.info(f"Blob video extracted successfully ({file_size} bytes) -> {output_path}")


async def poll_and_extract_video(page: Page, output_path: str, timeout: int = 360) -> str:
    """
    Polls the active page up to timeout seconds for video generation completion.
    Attempts extraction via:
      1. Direct in-page download button with page.expect_download()
      2. In-page <video> or <source> elements (blob or direct http)
    Also actively detects AI refusal or generation errors.
    """
    start_time = time.time()
    logger.info(f"Polling page for video completion (Timeout: {timeout}s)...")

    while (time.time() - start_time) < timeout:
        # 1. Check for AI error / refusal indicators
        for selector in ERROR_SELECTORS:
            try:
                err_el = page.locator(selector)
                if await err_el.count() > 0 and await err_el.first.is_visible():
                    err_text = await err_el.first.inner_text()
                    if err_text and len(err_text.strip()) > 0:
                        logger.error(f"Generation error detected in UI: {err_text}")
                        raise RuntimeError(f"Gemini generation error: {err_text.strip()}")
            except PlaywrightTimeoutError:
                pass

        # 2. Check for native download button
        download_buttons = page.locator(DOWNLOAD_BUTTON_SELECTOR)
        btn_count = await download_buttons.count()
        if btn_count > 0:
            target_btn = download_buttons.last
            try:
                if await target_btn.is_visible() and await target_btn.is_enabled():
                    logger.info("Found download button. Triggering native download...")
                    async with page.expect_download(timeout=15000) as download_info:
                        await target_btn.click()
                    download = await download_info.value
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                    await download.save_as(output_path)
                    logger.info(f"Video saved successfully via native download -> {output_path}")
                    return output_path
            except Exception as e:
                logger.warning(f"Native download attempt encountered issue: {e}. Falling back to DOM video inspection...")

        # 3. Check for HTML5 <video> elements
        video_elements = page.locator("video")
        video_count = await video_elements.count()
        if video_count > 0:
            last_video = video_elements.last
            try:
                # Retrieve video source attribute
                src = await last_video.get_attribute("src")
                if not src:
                    # Check <source> child tag
                    source_child = last_video.locator("source").first
                    if await source_child.count() > 0:
                        src = await source_child.get_attribute("src")

                if src:
                    src = src.strip()
                    if src.startswith("blob:"):
                        await extract_blob_video(page, src, output_path)
                        return output_path
                    elif src.startswith("http://") or src.startswith("https://"):
                        await download_file_from_url(src, output_path)
                        return output_path
            except Exception as e:
                logger.warning(f"Error inspecting video element: {e}")

        await asyncio.sleep(3)

    raise TimeoutError(f"Video generation timed out after {timeout} seconds without producing a downloadable video.")


async def generate_video(page: Page, prompt: str, output_path: str, timeout: int = 360) -> str:
    """
    High-level lifecycle for a single tab:
      1. Navigates to Gemini session.
      2. Injects the video prompt and submits.
      3. Polls until completion and extracts the video file.
    """
    await init_gemini_page(page)
    await inject_prompt(page, prompt)
    await submit_prompt(page)
    saved_path = await poll_and_extract_video(page, output_path=output_path, timeout=timeout)
    return saved_path
