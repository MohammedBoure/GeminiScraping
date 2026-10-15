import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright

# ضبط الترميز لبيئة Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ================= CONFIGURATION =================
OUTPUT_DIR = "./generated_videos"
DEBUG_PORT = 9222
GEMINI_URL = "https://gemini.google.com"
MAX_VIDEO_WAIT_TIME = 360  # أقصى مدة للانتظار بالثواني (الفيديو يستغرق وقتاً أطول من النصوص)
# =================================================

def ensure_video_mode(page):
    """
    التحقق من تفعيل وضع إنشاء الفيديو / الأدوات،
    أو فتح قائمة الأدوات/الإضافات إذا كانت الواجهة تتطلب ذلك صراحة.
    """
    print("[*] Checking / Setting Video mode...", flush=True)
    try:
        # البحث عن أزرار الأدوات أو الإضافات مثل Tools / Extensions / Create Video
        tool_btn = page.locator("button[aria-label*='Tools'], button[aria-label*='أدوات'], button:has-text('Tools')").first
        if tool_btn.is_visible(timeout=3000):
            tool_btn.click()
            time.sleep(1)
            # اختيار خيار الفيديو إذا كان موجوداً ضمن القائمة المنسدلة
            video_opt = page.locator("text=/Video|فيديو|Generate video/i").first
            if video_opt.is_visible(timeout=2000):
                video_opt.click()
                print("  [✓] Video tool selected successfully.", flush=True)
    except Exception:
        # في كثير من واجهات Gemini يكفي كتابة موجه توليد الفيديو مباشرة
        pass

def reset_chat_session(page):
    """فتح جلسة محادثة نظيفة."""
    print("\n[↺] Refreshing Gemini chat session...", flush=True)
    page.goto(GEMINI_URL)
    time.sleep(3.5)
    ensure_video_mode(page)

def inject_and_send_prompt(page, prompt: str):
    """حقن نص الموجه وإرساله بنفس آلية النص السابقة لتجنب مشاكل علامات التنصيص."""
    input_selector = "div.ql-editor.textarea, rich-textarea p, div[contenteditable='true'], textarea"
    
    try:
        page.locator(input_selector).first.wait_for(state="visible", timeout=12000)
    except Exception:
        reset_chat_session(page)
        page.locator(input_selector).first.wait_for(state="visible", timeout=12000)

    # حقن النص عبر JavaScript
    page.evaluate("""
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

    time.sleep(0.8)

    # الضغط على زر الإرسال أو زر Enter
    send_btn = page.locator("button[aria-label*='Send'], button[aria-label*='إرسال'], button.send-button, button.mat-mdc-unelevated-button").last
    if send_btn.is_visible() and send_btn.is_enabled():
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    print("  [~] Video prompt sent. Waiting for generation to complete...", flush=True)

def wait_for_video_and_download(page, filename: str) -> bool:
    """
    مراقبة الواجهة حتى اكتمال معالجة الفيديو واستخراجه أو تحميله.
    """
    waited = 0
    poll_interval = 5

    while waited < MAX_VIDEO_WAIT_TIME:
        time.sleep(poll_interval)
        waited += poll_interval

        # الحالة 1: وجود زر تحميل صريح بجانب الفيديو الناتج
        download_btn = page.locator("button[aria-label*='Download'], button[aria-label*='تنزيل'], a[download]").last
        if download_btn.is_visible():
            try:
                print(f"  [+] Found download button. Downloading '{filename}' via browser...", flush=True)
                with page.expect_download(timeout=10000) as download_info:
                    download_btn.click()
                download = download_info.value
                save_path = os.path.join(OUTPUT_DIR, filename)
                download.save_as(save_path)
                print(f"  [✓] Video saved directly to: {save_path}", flush=True)
                return True
            except Exception as e:
                print(f"  [!] Direct click download failed, attempting URL extraction: {e}", flush=True)

        # الحالة 2: ظهور وسم video واستخراج الرابط المباشر للملف (src أو blob)
        video_elements = page.locator("video, video source")
        count = video_elements.count()
        if count > 0:
            last_video = video_elements.nth(count - 1)
            video_src = last_video.get_attribute("src")

            if video_src and video_src.startswith("http"):
                print(f"  [+] Found direct video stream URL. Downloading...", flush=True)
                save_path = os.path.join(OUTPUT_DIR, filename)
                res = requests.get(video_src, stream=True)
                if res.status_code == 200:
                    with open(save_path, "wb") as f:
                        for chunk in res.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)
                    print(f"  [✓] Video downloaded successfully to: {save_path}", flush=True)
                    return True

            # إذا كان الرابط blob: URL، نقوم بسحبه مباشرة من الذاكرة عبر المتصفح
            elif video_src and video_src.startswith("blob:"):
                print(f"  [+] Extracting video from blob URL...", flush=True)
                save_path = os.path.join(OUTPUT_DIR, filename)
                video_base64 = page.evaluate("""
                    async (src) => {
                        const response = await fetch(src);
                        const blob = await response.blob();
                        return new Promise((resolve) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result.split(',')[1]);
                            reader.readAsDataURL(blob);
                        });
                    }
                """, video_src)

                import base64
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(video_base64))
                print(f"  [✓] Blob video saved to: {save_path}", flush=True)
                return True

        # التحقق مما إذا كانت هناك رسالة خطأ أو رفض لتوليد الفيديو
        error_indicators = page.locator("text=/I cannot generate|غير قادر على إنشاء|error generating/i")
        if error_indicators.count() > 0 and error_indicators.last.is_visible():
            print("  [X] Model returned an error or refused the prompt.", flush=True)
            return False

        print(f"  [...] Processing video... ({waited}s / {MAX_VIDEO_WAIT_TIME}s)", flush=True)

    print("  [!] Timed out waiting for video.", flush=True)
    return False

def generate_video(page, prompt: str, filename: str):
    """تنفيذ دورة العمل الكاملة لتوليد فيديو واحد."""
    print(f"\n==========================================")
    print(f"[*] Task: {filename}")
    print(f"[*] Prompt: {prompt[:60]}...")
    print(f"==========================================")

    inject_and_send_prompt(page, prompt)
    success = wait_for_video_and_download(page, filename)

    if not success:
        print(f"[!] Failed to generate/download: {filename}", flush=True)
    return success

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # قائمة بالمهام التي تريد توليدها
    video_tasks = [
        {
            "filename": "sunset_ocean.mp4",
            "prompt": "Create a high-quality cinematic realistic video of a calm ocean during golden hour sunset, 4k resolution."
        },
        {
            "filename": "futuristic_city.mp4",
            "prompt": "Generate a video showing flying cars between neon-lit skyscrapers in a cyberpunk city at night."
        }
    ]

    print("Connecting to running Chrome browser...")
    with sync_playwright() as p:
        try:
            # الاتصال بالمتصفح الجاري تشغيله عبر CDP
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        except Exception as e:
            print(f"\nCould not connect to Chrome! Make sure Chrome is open with --remote-debugging-port={DEBUG_PORT}")
            print(f"Details: {e}")
            sys.exit(1)

        default_context = browser.contexts[0]
        page = default_context.pages[0] if default_context.pages else default_context.new_page()

        print("[✓] Connected to Chrome successfully!")
        reset_chat_session(page)

        for task in video_tasks:
            generate_video(page, task["prompt"], task["filename"])
            # فاصل زمني لتجنب الـ Rate limits
            time.sleep(5)

        print("\n[★] All video tasks completed!")

if __name__ == "__main__":
    main()