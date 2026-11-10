# Скачивает расписание с lk.tolgas.ru и отправляет на GitHub.
# Запускается Планировщиком Windows (задача «Расписание ПВГУС — обновление»).
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = "D:\Claude\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("update-" + (Get-Date -Format "yyyy-MM") + ".log")
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Out-File -Append -Encoding utf8 $log }

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:PYTHONIOENCODING = "utf-8"
Set-Location $repo
Log "=== старт"

git pull -q --rebase origin main 2>&1 | ForEach-Object { Log "git: $_" }

$out = & python -I scripts/fetch.py 2>&1
$code = $LASTEXITCODE
$out | Select-Object -Last 5 | ForEach-Object { Log "fetch: $_" }
if ($code -ne 0) { Log "fetch завершился с кодом $code — сайт недоступен? Ничего не отправляю."; exit 1 }

git add data
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Log "изменений нет"; exit 0 }
git commit -q -m ("Обновить расписание " + (Get-Date -Format "yyyy-MM-dd HH:mm"))
git push -q origin main 2>&1 | ForEach-Object { Log "git: $_" }
if ($LASTEXITCODE -eq 0) { Log "отправлено на GitHub" } else { Log "ошибка git push" }
