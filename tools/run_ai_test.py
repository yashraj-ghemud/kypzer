import sys
from pathlib import Path
import json

# Ensure repo root is on sys.path so 'src' can be imported when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assistant.nlu import interpret


if __name__ == '__main__':
    plan = interpret("send diwali wishes to mummy with ai")
    print(json.dumps(plan, indent=2))
