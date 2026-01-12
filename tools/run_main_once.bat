@echo off
pushd "c:\Users\yashraj\Desktop\drawings\pc sontroller"
set PYTHONPATH=%CD%
python -m src.main --once "hi, how are you"
popd
