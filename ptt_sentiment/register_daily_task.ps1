<#
  註冊「股民溫度計_每日更新」排程：每天 08:45 經 run_daily_hidden.vbs 隱藏執行 daily_update.py。
  冪等：重跑會先移除舊工作再重建。只由使用者或協調者手動執行。
  08:45 的理由：前一個交易日的推文窗在今天 08:30 收尾，此時抓到的是完整一天。
#>
$ErrorActionPreference = "Stop"
$TaskName = "股民溫度計_每日更新"
$Dir = Split-Path $PSScriptRoot -Parent
$Vbs = Join-Path $PSScriptRoot "run_daily_hidden.vbs"
if (-not (Test-Path $Vbs)) { throw "找不到 $Vbs" }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
$Action = New-ScheduledTaskAction -Execute "C:\Windows\System32\wscript.exe" -Argument "//B //Nologo `"$Vbs`"" -WorkingDirectory $Dir
$Trigger = New-ScheduledTaskTrigger -Daily -At "08:45"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
# S4U 需提權，比照常駐狀態板用 Interactive
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal `
    -Description "股民溫度計：續抓 PTT 股版閒聊串、重建每日情緒表、提交並推送三個 CSV（金融戰情室）" | Out-Null
Write-Host "已註冊排程 [$TaskName]：每天 08:45"
