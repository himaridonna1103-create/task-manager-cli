# office_punch.ps1 — バーチャルオフィス打刻スクリプト
# Claude Code の hooks から呼ばれる：
#   PreToolUse (Skill/Agent/Task) → start : 稼働中リストに追加＋出勤ログ
#   Stop                          → stop  : 全員退勤＋退勤ログ
param([string]$Mode = "start")
$ErrorActionPreference = "SilentlyContinue"

$dataDir    = "C:\Users\karim\Claud 4.26\virtual-office\data"
$logFile    = Join-Path $dataDir "office_log.js"
$statusFile = Join-Path $dataDir "office_status.js"
$activeFile = Join-Path $dataDir "active.txt"

if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }
if (-not (Test-Path $logFile)) { Set-Content -Path $logFile -Value "window.OFFICE_LOG = [];" -Encoding UTF8 }

$now = Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"

function Write-Status([string[]]$names) {
  $items = @()
  foreach ($n in $names) { $items += ('{"name":"' + $n + '","since":"' + $now + '"}') }
  $body = 'window.OFFICE_STATUS = {"active":[' + ($items -join ",") + '],"updated":"' + $now + '"};'
  Set-Content -Path $statusFile -Value $body -Encoding UTF8
}

function Get-Active {
  if (Test-Path $activeFile) { return @(Get-Content $activeFile | Where-Object { $_ -ne "" }) }
  return @()
}

if ($Mode -eq "start") {
  $raw = [Console]::In.ReadToEnd()
  $name = ""
  try {
    $j = $raw | ConvertFrom-Json
    if ($j.tool_input.skill)             { $name = $j.tool_input.skill }
    elseif ($j.tool_input.subagent_type) { $name = $j.tool_input.subagent_type }
    elseif ($j.tool_name)                { $name = $j.tool_name }
  } catch {}
  if (-not $name) { $name = "claude" }
  # JSファイルへ書き込むため、名前は英数字と一部記号のみに制限（インジェクション防止）
  $name = ($name -replace '[^a-zA-Z0-9_\-:\.]', '')
  if (-not $name) { $name = "claude" }

  Add-Content -Path $logFile -Value ('OFFICE_LOG.push({t:"' + $now + '",name:"' + $name + '",ev:"start"});') -Encoding UTF8

  $active = @(Get-Active)
  if ($active -notcontains $name) { $active += $name }
  Set-Content -Path $activeFile -Value ($active -join [Environment]::NewLine) -Encoding UTF8
  Write-Status $active
}
elseif ($Mode -eq "stop") {
  $null = [Console]::In.ReadToEnd()
  $active = @(Get-Active)
  foreach ($n in $active) {
    Add-Content -Path $logFile -Value ('OFFICE_LOG.push({t:"' + $now + '",name:"' + $n + '",ev:"stop"});') -Encoding UTF8
  }
  Set-Content -Path $activeFile -Value "" -Encoding UTF8
  Write-Status @()
}

exit 0
