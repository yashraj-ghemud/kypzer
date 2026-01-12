import sys
import os

# Ensure repository root is on sys.path so `src` package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.assistant import nlu

cases = [
    "Hi how are you",
    "Turn Bluetooth on",
    "Send happy birthday to mom with ai",
    "Open chrome and search python unit testing",
    "Set volume to 30%",
]
for c in cases:
    out = nlu.interpret(c)
    print("INPUT:", c)
    print("OUTPUT:", out)
    print("---")
