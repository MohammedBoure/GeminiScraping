```markdown
# Gemini Web Trivia Generator (`web_gemini_generator.py`)

An automated pipeline utilizing Playwright via Chrome DevTools Protocol (CDP) to drive an active browser session on `gemini.google.com`. It autonomously creates trivia puzzle databases across multiple categories and topics into normalized JSON files.

---

## 1. Prerequisites & Dependencies

- **Python 3.10+**
- **Google Chrome** installed locally.
- Python dependencies:
  ```bash
  pip install playwright

```

---

## 2. Setting Up Remote Debugging (Chrome)

Before running the generator, you must launch an instance of Google Chrome with a remote debugging port enabled so Playwright can attach to your active Gemini session.

### Windows (PowerShell / CMD)

```powershell
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-dev-profile"

```

1. Navigate to `https://gemini.google.com` in the newly opened window.
2. Sign in to your Google Account.
3. Keep this browser window open in the background.

---

## 3. Configuration & Input File

The script expects a configuration input file named `categories.txt` in the root folder containing valid JSON structured by category and topic arrays:

```json
{
  "علوم": [
    "عالم البحار",
    "الكيمياء"
  ],
  "رياضه": [
    "كرة قدم",
    "الدوري الإسباني"
  ]
}

```

### Key Parameters in Script

* `CATEGORIES_FILE`: Path to the categories input (`categories.txt`).
* `OUTPUT_DIR`: Directory where output files are created (`./game_data/`).
* `QUESTIONS_PER_TOPIC`: Target questions per topic (default: `200`).
* `BATCH_SIZE`: Number of questions requested per prompt (default: `25`).
* `QUESTIONS_PER_CHAT`: Frequency of chat resets to avoid Error 1095 / server throttles (default: `400`).
* `DEBUG_PORT`: Target CDP port (`9222`).

---

## 4. How to Run

Execute the script in your terminal:

```bash
python web_gemini_generator.py

```

---

## 5. Output Schema

The generated data is stored under `./game_data/<category_id>/<topic_id>.json`. Each file adheres to the following structure:

```json
{
  "id": "علم_البحار",
  "categoryId": "science",
  "categoryTitle": "علوم",
  "title": "عالم البحار",
  "description": "عالم عالم البحار وعجائبه وأبرز أسراره وتحدياته",
  "cover_image": "/covers/علم_البحار.svg",
  "is_vip": false,
  "puzzles": [
    {
      "id": "علم__001",
      "prompt": "ما هو أكبر كائن حي يعيش في المحيطات؟",
      "answer_type": "text_normalized",
      "correct_answers": [
        "الحوت الازرق",
        "حوت ازرق",
        "الحوت الأزرق"
      ],
      "wrong_answers": [
        "القرش الأبيض الكبير",
        "الحوت القاتل",
        "حوت العنبر",
        "سبيدج عملاق",
        "فقمة الفيل",
        "قرش الحوت",
        "مانتا راي",
        "أخطبوط المحيط"
      ]
    }
  ]
}

```

---

## 6. Built-in Safeguards

* **Spelling Variant Expansion**: Automatically adds forms with and without `ال`, handles Arabic letters (`إ/أ/آ` -> `ا`, `ة` -> `ه`, `ى` -> `ي`), and Eastern/Western numeral equivalents.
* **Malformed JSON Recovery**: Employs multi-pass regex routines to repair unescaped inner quotation marks, smart Arabic quotes (`« » “ ”`), and trailing commas.
* **Session Cycling**: Automatically resets and refreshes the chat session when prompt quotas are met to prevent Google web rate limits (`Error 1095`).
* **Resumable Progress**: Inspects existing `.json` files on load; if a topic already contains questions, it resumes directly from that index without repeating work.
* **Anti-Stall Protection**: Skips topics with consecutive batch failures to prevent infinite retry loops.

```

```