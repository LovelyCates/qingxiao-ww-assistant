[CmdletBinding()]
param([ValidateSet('start','status','stop')][string]$Action='status',
      [ValidateSet('MC-Auto-probe','MC-Auto-daily','MC-Auto-weekly')][string]$TaskName='MC-Auto-probe',
      [string]$RequestId='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'Dispatch.ps1')
. (Join-Path $PSScriptRoot 'Task-Ownership.ps1')
try{
    $tasks=@(Get-ScheduledTask -TaskName 'MC-Auto-probe','MC-Auto-daily','MC-Auto-weekly' -ErrorAction Stop)
    foreach($task in $tasks){Assert-ManualTaskOwnership (Export-ScheduledTask -TaskName $task.TaskName) $root $task.TaskName}
    if($Action -eq 'status'){
        $result=@($tasks | ForEach-Object {
            [xml]$xml=Export-ScheduledTask -TaskName $_.TaskName
            $ns=New-Object Xml.XmlNamespaceManager($xml.NameTable)
            $ns.AddNamespace('t','http://schemas.microsoft.com/windows/2004/02/mit/task')
            [pscustomobject]@{Name=$_.TaskName;State=[string]$_.State;Triggers=@($xml.SelectNodes('//t:Triggers/*',$ns)).Count}
        })
        @{Ok=$true;Tasks=$result} | ConvertTo-Json -Depth 4 -Compress
    }elseif($Action -eq 'start'){
        if(@($tasks | Where-Object {$_.State -eq 'Running'}).Count){throw 'Another MC task is running.'}
        $request=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $root 'local-runs\pending-manual.json') | ConvertFrom-Json
        if($request.RequestId -ne $RequestId){throw 'The pending request has changed.'}
        $mode=$TaskName.Substring('MC-Auto-'.Length)
        $null=Get-ManualDispatch $request $mode
        Start-ScheduledTask -TaskName $TaskName
        @{Ok=$true;TaskName=$TaskName;RequestId=$RequestId} | ConvertTo-Json -Compress
    }else{
        Stop-ScheduledTask -TaskName $TaskName
        @{Ok=$true;Stopped=$TaskName} | ConvertTo-Json -Compress
    }
}catch{
    @{Ok=$false;Error=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
