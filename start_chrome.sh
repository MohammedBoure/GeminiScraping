#!/usr/bin/env bash
# ==============================================================================
# Script: start_chrome.sh
# Purpose: Launch Google Chrome / Chromium on Linux with remote debugging (9222)
# ==============================================================================

set -e

echo "========================================================"
echo "  Launching Chrome/Chromium with Remote Debugging (9222)"
echo "========================================================"

CHROME_BIN=""
CANDIDATES=(
    "$CHROME_BIN"
    "google-chrome-stable"
    "google-chrome"
    "chromium-browser"
    "chromium"
    "/usr/bin/google-chrome-stable"
    "/usr/bin/google-chrome"
    "/usr/bin/chromium-browser"
    "/usr/bin/chromium"
    "/snap/bin/chromium"
)

for bin in "${CANDIDATES[@]}"; do
    if [ -n "$bin" ] && command -v "$bin" >/dev/null 2>&1; then
        CHROME_BIN="$bin"
        break
    elif [ -n "$bin" ] && [ -x "$bin" ]; then
        CHROME_BIN="$bin"
        break
    fi
done

if [ -z "$CHROME_BIN" ]; then
    echo "[ERROR] Neither Google Chrome nor Chromium was found."
    echo "Please install Chrome or Chromium via:"
    echo "  sudo apt update && sudo apt install -y google-chrome-stable"
    echo "  # or: sudo apt install -y chromium-browser"
    echo "Or set the CHROME_BIN environment variable."
    exit 1
fi

PROFILE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gemini-chrome-profile"
mkdir -p "$PROFILE_DIR"

EXTRA_ARGS=""
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "[*] No display server detected (DISPLAY/WAYLAND_DISPLAY empty)."
    echo "[*] Automatically launching in headless mode..."
    EXTRA_ARGS="--headless=new --disable-gpu --disable-software-rasterizer"
fi

echo "[*] Found browser executable: $CHROME_BIN"
echo "[*] Profile directory:        $PROFILE_DIR"
echo "[*] Debugging port:           9222"
echo ""

# Launch browser in background detached
nohup "$CHROME_BIN" \
    --remote-debugging-port=9222 \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-setuid-sandbox \
    --disable-blink-features=AutomationControlled \
    $EXTRA_ARGS \
    "https://gemini.google.com" >/dev/null 2>&1 &

CHROME_PID=$!
echo "[✓] Browser launched in background (PID: $CHROME_PID)."
echo "[*] Listening on port 9222. Sign into Gemini if running in desktop mode."
