[CmdletBinding()]
param([ValidateSet('probe','daily','weekly','farm','echo','nightmare','assist','enhance','merge','multiaccount','mainstat','event')][string]$Mode='probe',
      [switch]$ValidateOnly,[string]$RequestFile='')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
. (Join-Path $PSScriptRoot 'manual_launcher\Dispatch.ps1')
$manualPath=Join-Path $PSScriptRoot 'local-runs\pending-manual.json'
if($RequestFile){if(-not $ValidateOnly){throw 'RequestFile is for validation only.'};$manualPath=$RequestFile}
$manualRequest=$null
$manualDispatch=$null
if(Test-Path -LiteralPath $manualPath){
    $manualRequest=Get-Content -Raw -Encoding UTF8 -LiteralPath $manualPath | ConvertFrom-Json
    $manualDispatch=Get-ManualDispatch $manualRequest $Mode
}
if($ValidateOnly){if(-not $manualDispatch){throw 'No manual request to validate.'};$Mode=$manualDispatch.Mode;$manualDispatch | ConvertTo-Json -Compress;return}
$gate=New-Object System.Threading.Mutex($false,'Local\MC-Local-Automation')
$ownsGate=$false
$runDir=$null
$process=$null
$code=$null
$wasTimedOut=$false
try{$ownsGate=$gate.WaitOne(0)}catch [System.Threading.AbandonedMutexException]{$ownsGate=$true}
if(-not $ownsGate){$gate.Dispose();throw 'Another MC automation run is active; no game was started.'}
try{
$runRoot=Join-Path $PSScriptRoot 'local-runs'
$invokedMode=$Mode
$farmTarget='tacet'
$reconcileRun=$null
$extraArgs=''
if($manualDispatch){
    $Mode=$manualDispatch.Mode
    if($Mode -eq 'farm'){$farmTarget=$manualDispatch.Action}
    $echoIndex=if($manualDispatch.Action -eq 'echo'){$manualDispatch.Index}else{1}
    $extraArgs=' --farm-index '+$manualDispatch.Index+' --simulation-material "'+$manualDispatch.Material+'" --echo-count '+$manualDispatch.Count+' --echo-index '+$echoIndex+' --echo-type '+$manualDispatch.Scope+' --nightmare-kind '+$manualDispatch.Kind
}
$farmRequestPath=Join-Path $runRoot 'pending-farm.json'
$useFarmRequest=$false
if(-not $manualDispatch -and $Mode -eq 'daily' -and (Test-Path -LiteralPath $farmRequestPath)){
    $farmRequest=Get-Content -Raw -Encoding UTF8 -LiteralPath $farmRequestPath | ConvertFrom-Json
    if($farmRequest.Operation -notin @('farm','farm_readback') -or $farmRequest.Target -notin @('tacet','simulation','forgery')){throw 'Invalid one-time farming request.'}
    if($farmRequest.Operation -eq 'farm_readback'){
        if($farmRequest.SourceRun -notmatch '^farm-\d{8}-\d{6}-\d{3}$'){throw 'Invalid farm readback identifier.'}
        $reconcileRun=$farmRequest.SourceRun
    }
    $requestAge=[DateTimeOffset]::Now-[DateTimeOffset]::Parse($farmRequest.CreatedAt)
    if($requestAge.TotalMinutes -gt 15 -or $requestAge.TotalMinutes -lt -1){throw 'One-time farming request expired; no action taken.'}
    $Mode='farm'
    $farmTarget=$farmRequest.Target
    $useFarmRequest=$true
}
$runId=$Mode+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$runDir=Join-Path $runRoot $runId
[IO.Directory]::CreateDirectory($runDir) | Out-Null
if($useFarmRequest){Move-Item -LiteralPath $farmRequestPath -Destination (Join-Path $runDir 'consumed-farm-request.json')}
if($manualDispatch){Move-Item -LiteralPath $manualPath -Destination (Join-Path $runDir 'manual-request.json')}
$report=Join-Path $runDir 'report.json'
$pointer=[ordered]@{Mode=$Mode;RunId=$runId;RunDirectory=$runDir;Report=$report;StartedAt=[DateTimeOffset]::Now.ToString('o')}
$pointer | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot ('latest-'+$Mode+'.json')) -Encoding UTF8
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$runner=Join-Path $PSScriptRoot 'local_runner.py'
# Stop only this project's leftover runners from the previously stopped task.
# Do not terminate any game process or unrelated Python process.
$leftovers=@(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like ('*'+$runner+'*')
})
if($leftovers.Count){
    $otherTasks=@(Get-ScheduledTask -TaskName 'MC-Auto-*' | Where-Object {$_.State -eq 'Running' -and $_.TaskName -ne ('MC-Auto-'+$invokedMode)})
    if($otherTasks.Count){throw 'Another MC task is running; leftover cleanup was skipped.'}
    $leftovers | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir 'previous-runners-stopped.json') -Encoding UTF8
    foreach($previous in $leftovers){Stop-Process -Id $previous.ProcessId -Force -ErrorAction SilentlyContinue}
}
$arguments='"'+$runner+'" --mode '+$Mode+' --report "'+$report+'"'
if($Mode -eq 'farm'){$arguments+=' --farm-target '+$farmTarget}
if($reconcileRun){$arguments+=' --reconcile-run '+$reconcileRun}
$arguments+=$extraArgs
if($manualDispatch){$arguments+=' --request-file "'+(Join-Path $runDir 'manual-request.json')+'"'}
$env:MC_RUN_OWNER_PID=[string]$PID
$env:MC_STOP_FILE=Join-Path $runDir 'stop-request.json'
$manualState=$null
if($manualDispatch){
    $manualState=[ordered]@{RequestId=$manualDispatch.RequestId;Action=$manualDispatch.Action;State='starting';TaskName=('MC-Auto-'+$invokedMode);Mode=$Mode;RunDirectory=$runDir;Report=$report;StartedAt=[DateTimeOffset]::Now.ToString('o')}
    $manualState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'manual-state.json') -Encoding UTF8
}
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'stdout.log') -RedirectStandardError (Join-Path $runDir 'stderr.log') -PassThru
$handle=$process.Handle
[ordered]@{ProcessId=$process.Id;ParentProcessId=$PID;Mode=$Mode;StartedAt=[DateTimeOffset]::Now.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir 'process-start.json') -Encoding UTF8
if($manualState){$manualState.State='running';$manualState['ProcessId']=$process.Id;$manualState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'manual-state.json') -Encoding UTF8}
$limit=if($Mode -eq 'probe'){600000}elseif($Mode -in @('assist','event') -and $manualRequest.Duration){([int]$manualRequest.Duration+5)*60000}else{5400000}
if(-not $process.WaitForExit($limit)){
    $wasTimedOut=$true
    $code=3
    $timedOut=[ordered]@{status='TIMEOUT';mode=$Mode;report=$report;process_id=$process.Id;at=[DateTimeOffset]::Now.ToString('o')}
    $timedOut | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir 'timeout.json') -Encoding UTF8
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    $process.WaitForExit()
    if($manualState){$manualState.State='timeout';$manualState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'manual-state.json') -Encoding UTF8}
    exit 3
}
$process.WaitForExit()
$code=$process.ExitCode
[ordered]@{ExitCode=$code;EndedAt=[DateTimeOffset]::Now.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDir 'process-result.json') -Encoding UTF8
if($manualState){$manualState.State=if($code -eq 0){'completed'}elseif($code -eq 4){'cancelled'}else{'failed'};$manualState['ExitCode']=$code;$manualState['EndedAt']=[DateTimeOffset]::Now.ToString('o');$manualState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'manual-state.json') -Encoding UTF8}
$process.Dispose()
exit $code
}catch{
    [IO.Directory]::CreateDirectory((Join-Path $PSScriptRoot 'local-runs')) | Out-Null
    [ordered]@{Error=$_.Exception.Message;Position=$_.InvocationInfo.PositionMessage;At=[DateTimeOffset]::Now.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local-runs\wrapper-error.json') -Encoding UTF8
    if($manualDispatch){[ordered]@{RequestId=$manualDispatch.RequestId;State='failed';Error=$_.Exception.Message;EndedAt=[DateTimeOffset]::Now.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local-runs\manual-state.json') -Encoding UTF8}
    throw
}finally{
    # A native OCR/capture crash can skip Python's finally block. Restore the
    # game's original transparency before releasing the permission task.
    if($runDir){
        $windowLease=Join-Path $runDir 'window-lease.json'
        if(Test-Path -LiteralPath $windowLease){
            try{
                $lease=Get-Content -Raw -Encoding UTF8 -LiteralPath $windowLease | ConvertFrom-Json
                if($lease.Active){& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'manual_launcher\restore_game_window.py') $windowLease | Set-Content -LiteralPath (Join-Path $runDir 'window-recovery.json') -Encoding UTF8}
            }catch{Write-Warning ('Window recovery: '+$_.Exception.Message)}
        }
        try{
            $finalCode=if($null -eq $code){1}else{$code}
            $finalArgs=@((Join-Path $PSScriptRoot 'manual_launcher\finalize_run.py'),$runDir,'--exit-code',[string]$finalCode)
            if($wasTimedOut){$finalArgs+='--timed-out'}
            & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') @finalArgs | Set-Content -LiteralPath (Join-Path $runDir 'finalization-result.json') -Encoding UTF8
        }catch{Write-Warning ('Report finalization: '+$_.Exception.Message)}
    }
    if($ownsGate){$gate.ReleaseMutex()};$gate.Dispose()
}
