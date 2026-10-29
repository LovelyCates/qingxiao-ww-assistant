$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$compiler=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if(-not (Test-Path -LiteralPath $compiler)){$compiler=Join-Path $env:SystemRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe'}
$icon=Join-Path $PSScriptRoot 'assets\qingxiao.ico'
if(-not (Test-Path -LiteralPath $icon)){$icon=Join-Path $PSScriptRoot 'assets\app.ico'}
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll (('/win32icon:')+$icon) (('/out:')+(Join-Path $root '鸣潮手动助手.exe')) (Join-Path $PSScriptRoot 'Launcher.cs')
if($LASTEXITCODE -ne 0){throw 'Launcher compilation failed.'}
Get-Item -LiteralPath (Join-Path $root '鸣潮手动助手.exe') | Select-Object FullName,Length
