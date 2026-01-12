# Build script for creating a single-file executable using PyInstaller
# Usage (PowerShell):
#   .\tools\build_exe.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root
Push-Location ".."

$venv_python = ".\.venv\Scripts\python.exe"
Write-Host "Using Python: $venv_python"

# Ensure PyInstaller is installed
& $venv_python -m pip install --upgrade pip setuptools wheel
& $venv_python -m pip install pyinstaller

# Run PyInstaller with the included spec file
& $venv_python -m PyInstaller kypzer.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build succeeded. See dist\kypzer.exe"
} else {
    Write-Host "Build failed. Check PyInstaller output above for errors." -ForegroundColor Red
}

Pop-Location
