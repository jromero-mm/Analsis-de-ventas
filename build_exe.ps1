$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$DistDir = Join-Path $ProjectDir "dist\AnalisisVentasDemo"
$ConfigSource = Join-Path $ProjectDir "config"
$ConfigTarget = Join-Path $DistDir "config"

Set-Location $ProjectDir
& $PythonExe -m PyInstaller --noconfirm --clean "AnalisisVentasDemo.spec"

New-Item -ItemType Directory -Force -Path $ConfigTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $ConfigSource "laboratorios.json") -Destination $ConfigTarget -Force
Copy-Item -LiteralPath (Join-Path $ConfigSource "concursos.json") -Destination $ConfigTarget -Force
if (Test-Path -LiteralPath (Join-Path $ConfigSource "perfiles.json")) {
    Copy-Item -LiteralPath (Join-Path $ConfigSource "perfiles.json") -Destination $ConfigTarget -Force
}

Write-Host "Ejecutable creado en: $DistDir\AnalisisVentasDemo.exe"
