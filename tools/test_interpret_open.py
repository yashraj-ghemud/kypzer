from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assistant.nlu import interpret
import json

cases = [
    "open notepad and type kitty",
    "open notepad and write kitty",
    "open notepad then write kitty",
    "open notepad and likho kitty",
]

for c in cases:
    print('INPUT:', c)
    print(json.dumps(interpret(c), indent=2))
    print('\n')
