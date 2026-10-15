# Core Automation Engine (`core/`)

This directory houses the foundational asynchronous Playwright/CDP modules for the multi-tab video generation worker system.

---

## 📁 File Manifest & Purpose

| File | Purpose |
|---|---|
| `__init__.py` | Package initialization exporting `JobManager`, `BrowserManager`, `generate_video`, `WorkerPool`, and `generate_oneshot`. |
| `job_manager.py` | Thread- and process-safe state and queue manager for `jobs.json` protected with atomic file locks (`filelock`). |
| `browser.py` | Asynchronous Playwright browser lifecycle manager connecting over CDP to `http://127.0.0.1:9222` and allocating isolated tabs (`Page` instances). |
| `gemini_page.py` | DOM interaction layer handling Gemini session navigation, JavaScript prompt injection, send triggers, refusal detection, and multi-strategy video extraction (native download, direct media URL, or base64 blob decoding). |
| `worker.py` | Asynchronous worker pool coordinating up to `N` concurrent tabs, dequeuing pending jobs, generating videos, handling timeouts/errors, and executing one-shot generations. |
| `README.md` | Directory documentation describing all modules and architectural responsibilities. |
