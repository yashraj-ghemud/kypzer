import sys
import os

# ensure workspace root is importable
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root not in sys.path:
    sys.path.insert(0, root)

import src.assistant.actions as actions

print('Module imported:', actions)

# Monkeypatch the whatsapp sender to avoid GUI
def _stub_whatsapp_send(contact, message):
    print(f"[STUB] whatsapp_send_message called with contact={contact!r}, message={message!r}")
    # Simulate success only if both provided and non-empty
    return bool(contact) and bool(message)

# Replace the function in the actions module
actions.whatsapp_send_message = _stub_whatsapp_send

# Test 1: explicit parameters
action = {"type": "whatsapp_send", "parameters": {"contact": "mumy", "message": "hi"}}
print('Running execute_action with explicit contact/message...')
res1 = actions.execute_action(action)
print('Result:', res1)

# Test 2: natural language
action2 = {"type": "whatsapp_send", "parameters": {"natural": "send hello to muumy"}}
print('\nRunning execute_action with natural text...')
res2 = actions.execute_action(action2)
print('Result:', res2)

# Exit status
ok = (res1.get('ok') or False) and (res2.get('ok') or False)
print('\nOverall ok:', ok)

if not ok:
    # Non-zero exit to make CI/tests notice
    raise SystemExit(2)
