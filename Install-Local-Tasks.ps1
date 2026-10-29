[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'"'
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -ArgumentList $arguments -WindowStyle Hidden | Out-Null
    return
}
$sid=$identity.User.Value
$shell=[Security.SecurityElement]::Escape("$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe")
$root=[Security.SecurityElement]::Escape($PSScriptRoot)
$installed=@()
foreach($mode in @('probe','daily','weekly')){
    $name='MC-Auto-'+$mode
    $taskArgs=[Security.SecurityElement]::Escape('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'Run-Local.ps1')+'" -Mode '+$mode)
    $xml=@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Local OK-WW $mode verification. On demand only; no daily trigger yet.</Description></RegistrationInfo>
<Triggers />
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><Enabled>true</Enabled><ExecutionTimeLimit>PT1H35M</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$shell</Command><Arguments>$taskArgs</Arguments><WorkingDirectory>$root</WorkingDirectory></Exec></Actions>
</Task>
"@
    if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw "Task already exists: $name; inspect it before replacing."}
    Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
    $installed+=$name
}
[IO.Directory]::CreateDirectory((Join-Path $PSScriptRoot 'local-runs')) | Out-Null
[ordered]@{InstalledAt=[DateTimeOffset]::Now.ToString('o');Tasks=$installed;DailyTriggerEnabled=$false;User=$identity.Name} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local-runs\task-setup.json') -Encoding UTF8
Write-Output 'Manual tasks installed. No game task was started.'
