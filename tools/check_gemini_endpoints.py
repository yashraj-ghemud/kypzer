from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assistant.config import settings
import requests
import json

key = settings.GEMINI_API_KEY or ''
print('GEMINI_API_KEY configured:', bool(key))
if key:
    print('GEMINI_API_KEY (masked):', key[:4] + '...' + key[-4:])
else:
    print('No GEMINI_API_KEY set in environment.')

models = [
    'gemini-2.5-flash',
    'gemini-1.5-flash',
]

for model in models:
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    print(f'\nTrying model: {model}\nPOST {url}?key=KEY')
    headers = {'Content-Type': 'application/json'}
    payload = {
        'contents': [
            {'role': 'user', 'parts': [{'text': 'Write a single friendly WhatsApp message: "Happy Diwali to my family"'}]}
        ]
    }
    params = {'key': key}
    try:
        r = requests.post(url, headers=headers, params=params, json=payload, timeout=20)
        print('Status:', r.status_code)
        try:
            data = r.json()
            # Pretty-print candidate text if present
            cand = None
            try:
                cand = data['candidates'][0]['content']['parts'][0]['text']
            except Exception:
                pass
            print('Response JSON (truncated):', json.dumps(data)[:1000])
            if cand:
                print('\nCandidate text (truncated):', cand[:400])
        except Exception:
            print('Response text (truncated):', (r.text or '')[:1000])
    except Exception as e:
        print('Request error:', e)

print('\nDone.')
