# Launch Google Chrome with remote debugging on port 9222
$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) {
    Write-Error "[ERROR] Google Chrome was not found in standard directories."
    exit 1
}

Write-Host "[*] Found Chrome at: $chrome" -ForegroundColor Cyan
Write-Host "[*] Launching Chrome on debugging port 9222..." -ForegroundColor Yellow

Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=C:\chrome-dev-profile",
    "https://gemini.google.com"
)

Write-Host "[OK] Chrome opened successfully. Sign in to Gemini and keep this window open!" -ForegroundColor Green
