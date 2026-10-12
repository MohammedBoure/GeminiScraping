import os
import sys
import json
import time
import re
import unicodedata
from playwright.sync_api import sync_playwright

# Enforce UTF-8 in Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ================= CONFIGURATION =================
CATEGORIES_FILE = "categories.txt"
OUTPUT_DIR = "./game_data"
QUESTIONS_PER_TOPIC = 200
BATCH_SIZE = 25              # Questions requested per prompt
QUESTIONS_PER_CHAT = 400     # Reset chat session every 400 total questions
DEBUG_PORT = 9222
# =================================================

CATEGORY_ID_MAP = {
    "منوعات": "general",
    "علوم": "science",
    "شهرة و فنون": "celebrities_arts",
    "رياضه": "sports",
    "دول و جغرافيا": "geography",
    "تاريخ و أدب": "history_literature",
    "العاب فيديو": "video_games",
    "أنمي و كرتون": "anime_cartoons",
    "أفلام و مسلسلات": "movies_series",
    "أزياء وموضة": "fashion"
}

# Global counter to track questions generated in the active chat session
questions_in_current_chat = 0

def make_clean_id(text: str) -> str:
    text = re.sub(r'[\u064B-\u0652]', '', text)
    text = re.sub(r'[^\w\s\u0600-\u06FF-]', '', text).strip()
    return text.replace(" ", "_")

def normalize_arabic(text: str) -> str:
    text = re.sub(r'[\u064B-\u0652]', '', text)
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text)
    return text.strip()

def generate_spelling_variants(answer: str) -> list[str]:
    variants = set()
    cleaned = str(answer).strip()
    variants.add(cleaned)
    norm = normalize_arabic(cleaned)
    variants.add(norm)

    if cleaned.startswith("ال") and len(cleaned) > 2:
        without_al = cleaned[2:].strip()
        variants.add(without_al)
        variants.add(normalize_arabic(without_al))
    else:
        with_al = "ال" + cleaned
        variants.add(with_al)
        variants.add(normalize_arabic(with_al))

    digit_map = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    rev_digit_map = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    if any(ch.isdigit() for ch in cleaned):
        variants.add(cleaned.translate(digit_map))
        variants.add(cleaned.translate(rev_digit_map))

    return [v for v in variants if v]

def extract_json_array(text: str) -> list:
    text = text.strip()

    # Extract block from markdown code fences if present
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if match:
        raw_json = match.group(1)
    else:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            raw_json = text[start:end + 1]
        else:
            raise ValueError("No JSON array delimiters found in response.")

    # Pass 1: Try direct parse
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        pass

    # Pass 2: Clean Arabic/smart quotes and trailing commas
    cleaned = raw_json
    cleaned = cleaned.replace("“", "'").replace("”", "'")
    cleaned = cleaned.replace("«", "'").replace("»", "'")
    cleaned = cleaned.replace("`", "'")
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Pass 3: Fix unescaped double quotes inside values
    lines = cleaned.splitlines()
    fixed_lines = []
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith('"prompt"') or stripped.startswith('"correct_answers"') or stripped.startswith('"wrong_answers"')) and stripped.count('"') > 4:
            parts = stripped.split('":')
            if len(parts) == 2:
                key, val = parts[0], parts[1]
                val_trimmed = val.strip()
                if val_trimmed.startswith('"') and val_trimmed.endswith(('",', '"')):
                    inner = val_trimmed[1:-2 if val_trimmed.endswith('",') else -1]
                    inner = inner.replace('"', "'")
                    suffix = '",' if val_trimmed.endswith('",') else '"'
                    line = f'{key}": "{inner}{suffix}'
        fixed_lines.append(line)

    repaired = "\n".join(fixed_lines)
    return json.loads(repaired)
def reset_chat_session(page):
    """Refreshes the page to launch a clean chat session."""
    global questions_in_current_chat
    print("\n[↺] Starting a new chat session on Gemini...", flush=True)
    page.goto("https://gemini.google.com")
    time.sleep(3.5)
    questions_in_current_chat = 0

def send_chat_prompt(page, prompt: str) -> list:
    global questions_in_current_chat

    # Reset chat if we reached or exceeded 400 questions in this chat context
    if questions_in_current_chat >= QUESTIONS_PER_CHAT:
        print(f"  [i] Reached limit of {QUESTIONS_PER_CHAT} questions in this chat. Resetting session.", flush=True)
        reset_chat_session(page)

    input_selector = "div.ql-editor.textarea, rich-textarea p, div[contenteditable='true'], textarea"
    try:
        page.locator(input_selector).first.wait_for(state="visible", timeout=12000)
    except Exception:
        # Retry once by refreshing the page if input is missing
        reset_chat_session(page)
        page.locator(input_selector).first.wait_for(state="visible", timeout=12000)

    # Safely inject text via evaluate without f-string quote collisions
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

    # Click the send button or press Enter
    send_btn = page.locator("button[aria-label*='Send'], button.send-button, button.mat-mdc-unelevated-button").last
    if send_btn.is_visible() and send_btn.is_enabled():
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    print(f"  [~] Prompt sent (Chat count: {questions_in_current_chat}/{QUESTIONS_PER_CHAT}). Waiting for response...", flush=True)
    time.sleep(4)

    max_wait = 120
    waited = 0
    last_text = ""
    stable_count = 0

    while waited < max_wait:
        responses = page.locator("message-content, model-response, .model-response-text")
        count = responses.count()
        if count > 0:
            current_text = responses.nth(count - 1).inner_text()
            if current_text and current_text == last_text:
                stable_count += 1
                if stable_count >= 3:  # Stream complete
                    try:
                        return extract_json_array(current_text)
                    except Exception:
                        pass
            else:
                stable_count = 0
                last_text = current_text

        time.sleep(2)
        waited += 2

    responses = page.locator("message-content, model-response, .model-response-text")
    if responses.count() > 0:
        return extract_json_array(responses.nth(responses.count() - 1).inner_text())

    raise TimeoutError("Model response timed out.")

def process_topic(page, cat_name: str, topic_name: str):
    global questions_in_current_chat

    cat_id = CATEGORY_ID_MAP.get(cat_name, make_clean_id(cat_name))
    topic_id = make_clean_id(topic_name)
    prefix = topic_id[:4]

    cat_folder = os.path.join(OUTPUT_DIR, cat_id)
    os.makedirs(cat_folder, exist_ok=True)
    target_file = os.path.join(cat_folder, f"{topic_id}.json")

    data = None
    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None

    if not data:
        data = {
            "id": topic_id,
            "categoryId": cat_id,
            "categoryTitle": cat_name,
            "title": topic_name,
            "description": f"عالم {topic_name} وعجائبه وأبرز أسراره وتحدياته",
            "cover_image": f"/covers/{topic_id}.svg",
            "is_vip": False,
            "puzzles": []
        }

    current_puzzles = data.get("puzzles", [])
    current_count = len(current_puzzles)

    if current_count >= QUESTIONS_PER_TOPIC:
        print(f"[-] Done: {topic_name} ({current_count}/{QUESTIONS_PER_TOPIC})", flush=True)
        return

    print(f"\n[+] Generating: {topic_name} ({current_count}/{QUESTIONS_PER_TOPIC})", flush=True)

    fails_in_row = 0
    while current_count < QUESTIONS_PER_TOPIC:
        batch_needed = min(BATCH_SIZE, QUESTIONS_PER_TOPIC - current_count)
        start_idx = current_count + 1

        prompt = f"""
أنت مصمم مسابقات وألعاب ذكاء باللغة العربية.
الموضوع: "{topic_name}" (قسم: "{cat_name}")

المطلوب:
أنشئ بالضبط {batch_needed} لغز أو سؤال جديد ومبتكر مع إجابات صحيحة وإجابات خاطئة واقعية ومضللة.

الإخراج يجب أن يكون JSON Array فقط تبدأ بـ [ وتنتهي بـ ]:
[
  {{
    "prompt": "صيغة السؤال بوضوح ودقة؟",
    "answer_type": "text_normalized",
    "correct_answers": ["الإجابة الصحيحة", "بدون أل التعريف", "مرادف شهير"],
    "wrong_answers": [
      "إجابة خاطئة 1",
      "إجابة خاطئة 2",
      "إجابة خاطئة 3",
      "إجابة خاطئة 4",
      "إجابة خاطئة 5",
      "إجابة خاطئة 6",
      "إجابة خاطئة 7",
      "إجابة خاطئة 8"
    ]
  }}
]

الشروط الإلزامية:
1. wrong_answers: يجب أن تحتوي بالضبط على 8 إجابات خاطئة ومضللة وواقعية جداً ومن نفس تصنيف وسياق السؤال.
2. answer_type: "number" إذا كانت الإجابة رقماً فقط، و"text_normalized" للنصوص.
3. لا تكتب أي مقدمات أو خاتمات أو أي كلام خارج مصفوفة الـ JSON الصريحة.
4. لا تستخدم علامات التنصيص المزدوجة " داخل نصوص الأسئلة أو الإجابات أبداً؛ استبدلها بأقواس () أو علامات فردية '.
5. يمنع منعاً باتاً تكرار أي سؤال أو صيغة أو معلومة سابقة، ويجب أن تكون كل الأسئلة فريدة وجديدة 100% ومتنوعة عبر محاور وزوايا مختلفة للموضوع.
6. تجنب تكرار نفس الإجابات الصحيحة في أسئلة متعددة داخل نفس الدفعة.
"""
        success = False
        for attempt in range(1, 3):
            try:
                chunk = send_chat_prompt(page, prompt)
                if not chunk or not isinstance(chunk, list):
                    raise ValueError("Output is not a valid list.")

                for idx, puz in enumerate(chunk, start=start_idx):
                    all_correct = set()
                    raw_correct = puz.get("correct_answers", [])
                    if isinstance(raw_correct, str):
                        raw_correct = [raw_correct]
                    for a in raw_correct:
                        all_correct.update(generate_spelling_variants(a))

                    raw_wrong = puz.get("wrong_answers", [])
                    if isinstance(raw_wrong, str):
                        raw_wrong = [raw_wrong]
                    clean_wrong = [str(w).strip() for w in raw_wrong if str(w).strip()][:8]

                    current_puzzles.append({
                        "id": f"{prefix}_{idx:03d}",
                        "prompt": str(puz.get("prompt", "")).strip(),
                        "answer_type": puz.get("answer_type", "text_normalized"),
                        "correct_answers": list(all_correct),
                        "wrong_answers": clean_wrong
                    })

                data["puzzles"] = current_puzzles
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                generated_count = len(chunk)
                current_count = len(current_puzzles)
                
                questions_in_current_chat += generated_count

                print(f"  [✓] Saved {current_count}/{QUESTIONS_PER_TOPIC} in {topic_name} (Session Total: {questions_in_current_chat}/{QUESTIONS_PER_CHAT})", flush=True)
                success = True
                fails_in_row = 0
                break

            except Exception as e:
                print(f"  [!] Attempt {attempt}/2 error: {e}", flush=True)
                time.sleep(4)

        if not success:
            fails_in_row += 1
            print(f"[X] Batch failed for {topic_name} (Fail count: {fails_in_row})", flush=True)
            if fails_in_row >= 2:
                print(f"[!] Skipping stuck topic {topic_name}.", flush=True)
                break
            time.sleep(6)

        time.sleep(2)

def main():
    if not os.path.exists(CATEGORIES_FILE):
        print(f"Error: {CATEGORIES_FILE} not found.")
        sys.exit(1)

    with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
        categories = json.load(f)

    print("Connecting to running Chrome browser...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        except Exception as e:
            print(f"\nCould not connect to Chrome! Make sure Chrome is open with --remote-debugging-port={DEBUG_PORT}")
            print(f"Details: {e}")
            sys.exit(1)

        default_context = browser.contexts[0]
        page = default_context.pages[0] if default_context.pages else default_context.new_page()

        print("[✓] Connected to Chrome successfully!")
        
        # Open initial clean chat session
        reset_chat_session(page)

        for cat_name, topics in categories.items():
            for topic in topics:
                process_topic(page, cat_name, topic)

        print("\n[★] Finished generating database via web automation!")

if __name__ == "__main__":
    main()