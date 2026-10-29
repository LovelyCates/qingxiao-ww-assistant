function Assert-ManualTaskOwnership {
    param([string]$TaskXml,[string]$Root,[string]$TaskName)
    [xml]$task=$TaskXml
    $actions=@($task.Task.Actions.Exec)
    if($actions.Count -ne 1){throw 'Permission task must contain exactly one action.'}
    $exec=$actions[0]
    if(-not $exec.WorkingDirectory){throw 'Permission task has no project directory.'}
    $expectedRoot=[IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $actualRoot=[IO.Path]::GetFullPath([string]$exec.WorkingDirectory).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $mode=$TaskName.Substring('MC-Auto-'.Length)
    $runner=Join-Path $expectedRoot 'Run-Local.ps1'
    $expectedArgs='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$runner+'" -Mode '+$mode
    $expectedShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if(-not [string]::Equals($expectedRoot,$actualRoot,[StringComparison]::OrdinalIgnoreCase) -or
       -not [string]::Equals($expectedArgs,([string]$exec.Arguments).Trim(),[StringComparison]::OrdinalIgnoreCase) -or
       -not [string]::Equals($expectedShell,[string]$exec.Command,[StringComparison]::OrdinalIgnoreCase)){
        throw 'Permission task belongs to another project directory or has unexpected arguments; no task was started or stopped.'
    }
}
