[CmdletBinding()]
param([string]$Python='py',[switch]$UsePip,[switch]$FetchResources)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$root=$PSScriptRoot
$pythonArgs=@()
if([IO.Path]::GetFileNameWithoutExtension($Python) -eq 'py'){$pythonArgs=@('-3.12')}
try{$version=& $Python @pythonArgs -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46))'}catch{throw 'Install 64-bit Python 3.12, or pass -Python with its executable path.'}
if($LASTEXITCODE -ne 0 -or $version -ne '3.12'){throw 'This candidate is tested with Python 3.12 only.'}
$resolvedPython=& $Python @pythonArgs -c 'import sys; print(sys.executable)'
if($LASTEXITCODE -ne 0){throw 'Unable to resolve Python interpreter.'}
$venv=Join-Path $root '.venv'
$venvPython=Join-Path $venv 'Scripts\python.exe'
$uv=if(-not $UsePip){Get-Command uv -ErrorAction SilentlyContinue}else{$null}
if($uv){
    if(-not (Test-Path -LiteralPath $venvPython)){& $uv.Source venv --python $resolvedPython $venv;if($LASTEXITCODE -ne 0){throw 'Virtual environment creation failed.'}}
    & $uv.Source pip sync --python $venvPython --index-url 'https://pypi.org/simple' (Join-Path $root 'requirements.lock.txt')
    if($LASTEXITCODE -ne 0){throw 'Dependency installation failed.'}
    & $uv.Source pip check --python $venvPython
}else{
    if(-not (Test-Path -LiteralPath $venvPython)){& $Python @pythonArgs -m venv $venv;if($LASTEXITCODE -ne 0){throw 'Virtual environment creation failed.'}}
    & $venvPython -m ensurepip --upgrade
    if($LASTEXITCODE -ne 0){throw 'pip bootstrap failed.'}
    & $venvPython -m pip install --index-url 'https://pypi.org/simple' -r (Join-Path $root 'requirements.lock.txt')
    if($LASTEXITCODE -ne 0){throw 'Dependency installation failed.'}
    & $venvPython -m pip check
}
if($LASTEXITCODE -ne 0){throw 'Dependency compatibility check failed.'}
if($FetchResources){
    & $venvPython -I (Join-Path $root 'release_tools\fetch_upstream_resources.py')
    if($LASTEXITCODE -ne 0){throw 'Upstream resource download/checksum verification failed.'}
}
& (Join-Path $root 'manual_launcher\Build.ps1')
& $venvPython -I (Join-Path $root 'release_tools\smoke_test.py')
if($LASTEXITCODE -ne 0){throw 'Isolated UI smoke test failed.'}
Write-Output 'Setup and isolated UI checks passed. No game or permission task was started.'
