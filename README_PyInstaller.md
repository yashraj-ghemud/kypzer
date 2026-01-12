PyInstaller build instructions

This repository is a Python Tkinter app. To build a Windows executable (one-file, windowed) using PyInstaller from the project's venv, follow these steps:

1. Activate your virtual environment (Windows PowerShell):

   & ".\.venv\Scripts\Activate.ps1"

2. Install PyInstaller into the environment if not already installed:

   pip install pyinstaller

3. From the repository root run PyInstaller with the following options:

   pyinstaller --onefile --windowed -n "PCController" src\main.py

- --onefile bundles everything into a single exe.
- --windowed prevents a console window from appearing.
- -n sets the output name.

4. After the build completes, the executable will be available in the `dist` folder: `dist\PCController.exe`.

Notes and tips
- If your app uses additional data files, icons, or non-Python assets, add them using the `--add-data` flag or a spec file.
- For icons: `--icon=assets\app.ico`.
- Test the built exe on a clean Windows install (or VM) to ensure that any native dependencies (e.g. pyttsx3 voices) are available.

If you'd like, I can create a basic PowerShell build script next to the README that runs these commands automatically from the repo root.