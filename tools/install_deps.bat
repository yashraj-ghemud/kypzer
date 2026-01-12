@echo off
pushd "C:\Users\yashraj\Desktop\drawings\pc sontroller"
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python.exe -m pip install -r requirements.txt pyttsx3
popd
