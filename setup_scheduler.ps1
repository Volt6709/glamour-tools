# Run this once as Administrator to schedule daily invoice reminders.
# Right-click setup_scheduler.ps1 → "Run with PowerShell" (as Admin)

$taskName   = "GlamourTools - Invoice Reminders"
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$batFile    = Join-Path $scriptDir "reminders.bat"
$logFile    = Join-Path $scriptDir "reminders.log"
$runAt      = "09:00"   # 9:00 AM daily — change if needed

$action  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batFile`" >> `"$logFile`" 2>&1"

$trigger = New-ScheduledTaskTrigger -Daily -At $runAt

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force

Write-Host ""
Write-Host "Done. Task '$taskName' scheduled daily at $runAt." -ForegroundColor Green
Write-Host "Logs will be written to: $logFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test it now, run:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Yellow
