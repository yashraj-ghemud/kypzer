# PowerShell script to build a single-file windowed exe using the venv's python and PyInstaller
$venvPython = "$PWD\.venv\Scripts\python.exe"
if (-Not (Test-Path $venvPython)) {
    Write-Error "Virtualenv python not found at $venvPython. Activate your venv or adjust the path."
    exit 1
}
& $venvPython -m pip install --upgrade pip pyinstaller
# include icon if present
$iconPath = Join-Path $PWD "assets\app.ico"
if (Test-Path $iconPath) {
    Write-Host "Found icon at $iconPath, including in build"
    & $venvPython -m PyInstaller --onefile --windowed -n "kypzer" --icon "$iconPath" --hidden-import "comtypes" --hidden-import "pyttsx3.drivers" --hidden-import "pyttsx3.drivers.sapi5" src\main.py
} else {
    & $venvPython -m PyInstaller --onefile --windowed -n "kypzer" --hidden-import "comtypes" --hidden-import "pyttsx3.drivers" --hidden-import "pyttsx3.drivers.sapi5" src\main.py
}
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller build failed"; exit $LASTEXITCODE }
Write-Host "Build finished. See dist\kypzer.exe"