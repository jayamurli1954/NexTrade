# Daily launcher for NexTrade paper trading with ONE Angel login (no broker orders).
# Run by Windows Task Scheduler at ~09:05 Mon-Fri.
#
#  * Dashboard already open  -> do nothing: the dashboard auto-starts the options paper lane itself
#                               (config\options_paper.json "auto_start": true) on its own Angel login.
#  * Dashboard not open      -> open it (python launch_dashboard.py). It logs in once, runs equity paper
#                               trading as usual, and auto-starts the options paper lane.
#  * -Standalone             -> old behaviour: run only the options lane in its own process (its own login).

param([switch]$Standalone)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$python = $env:NEXTRADE_PYTHON
if (-not $python) { $python = "python" }

$logDir = Join-Path $repo "logs\options_paper"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("launcher_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))
function Write-Log($msg) { "$(Get-Date -Format s)  $msg" | Out-File -FilePath $log -Append -Encoding utf8 }

if ((Get-Date).DayOfWeek -in @("Saturday", "Sunday")) { Write-Log "Weekend - nothing to do."; exit 0 }

if ($Standalone) {
    Write-Log "Standalone options lane (separate Angel login)."
    & $python -m trading_app.options_paper.runner --config "config\options_paper.json" *>> (Join-Path $logDir ("runner_{0}.log" -f (Get-Date -Format "yyyy-MM-dd")))
    exit $LASTEXITCODE
}

foreach ($port in 8580, 8581, 8582, 8590) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/heartbeat" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            Write-Log "Dashboard already running on port $port - it auto-starts the options lane on its own login."
            exit 0
        }
    } catch { }
}

Write-Log "Dashboard not running - starting it (single Angel login; options lane auto-starts)."
$out = Join-Path $logDir ("dashboard_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))
$env:PYTHONIOENCODING = "utf-8"   # dashboard console output goes to a file; avoid cp1252 print errors
Start-Process -FilePath $python -ArgumentList "launch_dashboard.py" -WorkingDirectory $repo `
    -WindowStyle Minimized -RedirectStandardOutput $out -RedirectStandardError ($out + ".err")
exit 0
