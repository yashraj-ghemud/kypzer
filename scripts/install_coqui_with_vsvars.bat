@echo off
REM Load MSVC environment and install Coqui TTS + audio deps into .venv311
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
echo MSVC env set. Python executable: .\.venv311\Scripts\python.exe
.".\.venv311\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel cython
.".\.venv311\Scripts\python.exe" -m pip install TTS soundfile simpleaudio numpy
echo Installation finished. Running coqui_runner test (synthesize sample)...
.".\.venv311\Scripts\python.exe" "src\assistant\coqui_runner.py" --text "Namaste, main Viczo hoon — batao kaise madad karoon?" --out "test_coqui.wav"
echo coqui_runner finished.
pause
