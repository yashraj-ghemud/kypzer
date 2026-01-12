from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assistant.config import settings
from src.assistant.nlu import _gemini_plan
import json

print('GEMINI_API_KEY configured:', bool(settings.GEMINI_API_KEY))
if settings.GEMINI_API_KEY:
    masked = settings.GEMINI_API_KEY[:4] + '...' + settings.GEMINI_API_KEY[-4:]
else:
    masked = ''
print('GEMINI_API_KEY (masked):', masked)

print('\nCalling _gemini_plan with a short test prompt (timeout=20s) ...')
plan = _gemini_plan('Write a single friendly WhatsApp message: "Happy Diwali to my family"', memory=None)
print(json.dumps(plan, indent=2))
