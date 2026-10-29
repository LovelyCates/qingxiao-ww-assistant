function Get-ManualDispatch {
    param($Request,[string]$InvokedMode)
    if($Request.Version -ne 1 -or $Request.RequestId -notmatch '^[0-9a-fA-F-]{36}$'){throw 'Invalid manual request identifier.'}
    $actions=@('probe','daily','tacet','forgery','simulation','weekly','echo','nightmare','pickup','dialog','combat','enhance','merge','multiaccount','reconstruct','elimination','fasttravel','quest')
    if($Request.Action -notin $actions){throw 'Unknown manual action.'}
    if($Request.Action -eq 'multiaccount'){
        if($Request.Accounts -isnot [array] -or $Request.Accounts.Count -lt 1 -or $Request.Accounts.Count -gt 10){throw 'Invalid account snapshot.'}
        if($Request.Background -ne 'foreground'){throw 'Account switching requires foreground mode.'}
    }elseif($null -ne $Request.Accounts){throw 'Accounts are only valid for the account executor.'}
    if($null -ne $Request.ValidationScene -and -not (($Request.Action -eq 'multiaccount' -and $Request.ValidationScene -eq 'account_inventory') -or ($Request.Action -eq 'pickup' -and $Request.ValidationScene -eq 'pickup_echo') -or ($Request.Action -eq 'combat' -and $Request.ValidationScene -in @('combat_boss','combat_tacet')) -or ($Request.Action -eq 'dialog' -and $Request.ValidationScene -eq 'dialog_phone') -or ($Request.Action -eq 'enhance' -and $Request.ValidationScene -in @('echo_inventory','echo_current_resume')))){throw 'Invalid fixed validation scene.'}
    if($Request.ValidationScene -eq 'echo_current_resume' -and $Request.Count -ne 1){throw 'Resume is limited to the current candidate.'}
    if($Request.ValidationScene -eq 'echo_current_resume' -and $Request.CheckOnly){throw 'Resume cannot use the generic inventory preflight.'}
    if($null -ne $Request.TargetLimit -and ($Request.Action -ne 'nightmare' -or ($Request.TargetLimit -isnot [int] -and $Request.TargetLimit -isnot [long]) -or $Request.TargetLimit -lt 1 -or $Request.TargetLimit -gt 100)){throw 'Invalid nest target limit.'}
    if($null -ne $Request.StaminaLimit){
        $cost=if($Request.Action -eq 'tacet'){60}else{40}
        if($Request.Action -notin @('tacet','forgery','simulation') -or ($Request.StaminaLimit -isnot [int] -and $Request.StaminaLimit -isnot [long]) -or $Request.StaminaLimit -lt $cost -or $Request.StaminaLimit -gt 240 -or $Request.StaminaLimit % $cost){throw 'Invalid natural stamina limit.'}
    }
    $age=[DateTimeOffset]::Now-[DateTimeOffset]::Parse($Request.CreatedAt)
    if($age.TotalSeconds -gt 120 -or $age.TotalSeconds -lt -10){throw 'Manual request expired. Click the button again.'}
    $expected=if($Request.Action -eq 'probe'){'probe'}elseif($Request.Action -eq 'weekly'){'weekly'}else{'daily'}
    if($InvokedMode -ne $expected){throw 'Request does not match the selected permission task.'}
    if($Request.Scope -notin @('boss','weekly','nightmare') -or $Request.Kind -notin @('all','purification','nest')){throw 'Invalid farming selection.'}
    if($Request.Material -notin @('Shell Credit','Resonator EXP','Weapon EXP')){throw 'Invalid simulation material.'}
    if($Request.Index -isnot [int] -and $Request.Index -isnot [long]){throw 'Target index must be an integer.'}
    if($Request.Count -isnot [int] -and $Request.Count -isnot [long]){throw 'Repeat count must be an integer.'}
    $maxIndex=if($Request.Action -eq 'tacet'){21}elseif($Request.Action -eq 'forgery'){20}elseif($Request.Scope -eq 'weekly'){9}elseif($Request.Scope -eq 'nightmare'){10}else{20}
    if($Request.Action -eq 'daily' -and $null -ne $Request.DailyFarm){$maxIndex=if($Request.DailyFarm -eq 'tacet'){21}elseif($Request.DailyFarm -eq 'forgery'){20}else{1}}
    if($Request.Index -lt 1 -or $Request.Index -gt $maxIndex -or $Request.Count -lt 1 -or $Request.Count -gt 100){throw 'Target index or repeat count is out of range.'}
    if($Request.Action -in @('enhance','merge','reconstruct') -and $Request.CheckOnly -ne $true -and $Request.ConfirmedMaterials -ne $true){throw 'Material-consuming tasks need explicit confirmation in the panel.'}
    if($Request.Action -eq 'reconstruct' -and $Request.MainStat -notin @('攻击','暴击伤害','暴击','生命','防御','共鸣效率','冷凝伤害加成','热熔伤害加成','导电伤害加成','气动伤害加成','衍射伤害加成','湮灭伤害加成')){throw 'Invalid reconstruction target.'}
    if($null -ne $Request.DailyFarm -and ($Request.Action -ne 'daily' -or $Request.DailyFarm -notin @('tacet','forgery','simulation'))){throw 'Invalid daily target.'}
    if($null -ne $Request.Duration -and (($Request.Duration -isnot [int] -and $Request.Duration -isnot [long]) -or $Request.Duration -lt 1 -or $Request.Duration -gt 180)){throw 'Invalid assistant duration.'}
    if($null -ne $Request.Background -and $Request.Background -notin @('foreground','background','hidden')){throw 'Invalid window behavior.'}
    if($null -ne $Request.CheckOnly -and ($Request.CheckOnly -isnot [bool] -or ($Request.CheckOnly -and $Request.Action -notin @('weekly','enhance','merge','reconstruct','elimination')))){throw 'Invalid read-only check.'}
    $mode=if($Request.Action -in @('tacet','forgery','simulation')){'farm'}elseif($Request.Action -in @('pickup','dialog','combat','fasttravel','quest')){'assist'}elseif($Request.Action -eq 'reconstruct'){'mainstat'}elseif($Request.Action -eq 'elimination'){'event'}else{$Request.Action}
    [pscustomobject]@{Mode=$mode;Action=$Request.Action;Index=[int]$Request.Index;Count=[int]$Request.Count;Material=$Request.Material;Scope=$Request.Scope;Kind=$Request.Kind;RequestId=$Request.RequestId}
}
