# Gemini Automation Platform: Video Generation Worker & Trivia Pipeline

A high-performance, asynchronous automation framework built on **Playwright** via Chrome DevTools Protocol (CDP) at `http://127.0.0.1:9222`.

The platform provides:
1. **Asynchronous Multi-Tab Video Generation Worker & Queue System**: Orchestrates up to $N$ concurrent tabs to generate and download AI videos with atomic file locking (`jobs.json`) and an agent-ready CLI (`cli.py`).
2. **Trivia Puzzle Pipeline (`web_gemini_generator.py`)**: Automates high-volume trivia puzzle generation across diverse categories into structured JSON datasets.

---

## 📁 Repository Structure & File Manifest

| File / Directory | Purpose & Responsibility |
|---|---|
| `cli.py` | Unified Agent CLI supporting human-readable output and machine-readable `--json` responses (`submit`, `status`, `list`, `start-worker`, `generate`). |
| `core/` | Asynchronous automation engine package. Contains `job_manager.py`, `browser.py`, `gemini_page.py`, `worker.py`, and `__init__.py`. |
| `core/job_manager.py` | Thread- and process-safe state manager for `jobs.json` backed by `filelock`. |
| `core/browser.py` | Async CDP connection manager (`http://127.0.0.1:9222`) handling tab pool allocation and isolation. |
| `core/gemini_page.py` | DOM interaction, JS prompt injection, refusal detection, and multi-strategy video extraction (native download, direct URL, base64 blob decoding). |
| `core/worker.py` | Multi-tab worker pool coordinator and one-shot execution handler. |
| `core/README.md` | Dedicated documentation for the `core/` modules. |
| `jobs.json` | Persistent state tracking queue for video generation jobs. |
| `start_chrome.ps1` | PowerShell script to launch Google Chrome with remote debugging on port `9222`. |
| `start_chrome.bat` | Batch script to launch Google Chrome on port `9222` with a dedicated profile. |
| `run_generator.bat` | Convenience batch runner for the trivia generator. |
| `requirements.txt` | Project dependencies (`playwright`, `filelock`, `requests`, `aiohttp`). |
| `web_gemini_generator.py` | High-volume trivia question generator pipeline. |
| `web_gemini_video_generator.py` | Standalone synchronous single-task video generator script. |
| `README.md` | Main platform documentation, setup instructions, and CLI reference. |

---

## 1. Architecture & Key Features

- **Multi-Tab Concurrency**: Uses `playwright.async_api` connected to an existing Chrome instance. Spawns up to $N$ worker tabs simultaneously (default: 3).
- **Tab Isolation**: Every generation task receives its own isolated page (`context.new_page()`) that is cleanly closed upon completion or error.
- **Atomic Job Queue (`jobs.json`)**: Thread- and process-safe state transitions (`pending` ➔ `processing` ➔ `completed` / `failed`) guarded by `filelock.FileLock`.
- **Tri-Strategy Video Extraction**:
  1. *Native Download Triggers*: Intercepts browser download events via `page.expect_download()`.
  2. *Direct Media URLs*: Downloads HTTP/HTTPS video streams asynchronously using `aiohttp`.
  3. *In-Page Blob Decoding*: Fetches `blob:` URLs directly within page context via JavaScript and encodes to base64, then decodes and writes to disk.
- **Agent-Friendly CLI**: Every command features a `--json` flag outputting pure, unpolluted JSON on `stdout` while diagnostic logs are routed to `stderr`.

---

## 2. Setup & Installation

### Prerequisites
- **Python 3.10 – 3.12**
- **Google Chrome** installed locally.

### Installation
```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
playwright install chromium
```

---

## 3. Launching Google Chrome in Debugging Mode

Before running any workers or one-shot commands, launch Chrome with remote debugging enabled:

**PowerShell:**
```powershell
.\start_chrome.ps1
```

**CMD / Batch:**
```cmd
start_chrome.bat
```

> [!IMPORTANT]
> 1. Sign in to your Google Account on `https://gemini.google.com` in the opened Chrome window.
> 2. Keep this browser window running in the background.

---

## 4. CLI Reference (`cli.py`)

The CLI offers standard human-readable format or pure JSON (`--json`) for automated agents.

### A. Submit a Video Generation Job
Enqueues a new prompt to `jobs.json`:
```bash
python cli.py submit --prompt "Cinematic drone shot of an emerald tropical island" --filename "island.mp4" --json
```
**JSON Response:**
```json
{
  "job_id": "vid_20261016_010000_abc123",
  "status": "pending",
  "output_path": "generated_videos\\island.mp4",
  "prompt": "Cinematic drone shot of an emerald tropical island"
}
```

### B. Check Job Status
Inspect details and progress of a specific job:
```bash
python cli.py status vid_20261016_010000_abc123 --json
```
**JSON Response:**
```json
{
  "job_id": "vid_20261016_010000_abc123",
  "prompt": "Cinematic drone shot of an emerald tropical island",
  "filename": "island.mp4",
  "status": "completed",
  "created_at": 1729040000.0,
  "started_at": 1729040002.5,
  "completed_at": 1729040045.2,
  "error": null,
  "output_path": "generated_videos\\island.mp4"
}
```

### C. List Jobs
Query all or filter by status (`pending`, `processing`, `completed`, `failed`):
```bash
python cli.py list --status pending --json
```

### D. Start Concurrent Worker Pool
Runs the background consumer orchestrating multiple tabs simultaneously:
```bash
python cli.py start-worker --max-tabs 3 --timeout 360
```

### E. One-Shot Generation
Blocks until video generation and download finish:
```bash
python cli.py generate --prompt "Hyperlapse of neon Tokyo at night" --output "./generated_videos/tokyo.mp4" --json
```

---

## 5. Autonomous Agent One-Liners

Autonomous LLM agents can control video generation using standard subprocess commands:

### Submit and Poll Until Done (PowerShell)
```powershell
$job = (python cli.py submit --prompt "Close up macro of honey bee on lavender" --json | ConvertFrom-Json)
Write-Host "Submitted job: $($job.job_id)"
do {
    Start-Sleep -Seconds 5
    $status = (python cli.py status $job.job_id --json | ConvertFrom-Json)
} while ($status.status -in @("pending", "processing"))
Write-Host "Job finished with status: $($status.status). Output: $($status.output_path)"
```

### Submit and Poll Until Done (Bash / Python Subprocess)
```bash
JOB_ID=$(python cli.py submit --prompt "Cyberpunk street market in the rain" --json | jq -r '.job_id')
while :; do
  STATUS=$(python cli.py status "$JOB_ID" --json | jq -r '.status')
  [ "$STATUS" = "completed" ] && break
  [ "$STATUS" = "failed" ] && exit 1
  sleep 5
done
echo "Video ready at: $(python cli.py status "$JOB_ID" --json | jq -r '.output_path')"
```

---

## 6. Trivia Generator Pipeline (`web_gemini_generator.py`)

To run the trivia question dataset scraper:
```powershell
.\.venv\Scripts\python.exe web_gemini_generator.py
```
- Inputs: `categories.txt`
- Outputs: Normalized JSON files under `./game_data/<category>/<topic>.json` adhering to `example of the result.json`.