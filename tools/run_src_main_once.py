import os
import sys
import traceback

# Ensure project root is on sys.path
ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

print("Running one-shot test: src.main --once 'idhar likh bhaii'\n")

try:
    from src import main
except Exception as e:
    print("Failed to import src.main:", e)
    traceback.print_exc()
    raise

text = "idhar likh bhaii"
print("User input:", text)
try:
    plan = main.interpret(text)
    print("Interpret plan:", plan)
    resp = plan.get('response', '')
    actions = plan.get('actions', [])

    # Try to get viczo brain via helper if available
    viczo = None
    try:
        # main._get_viczo_brain exists in src.main; it's a lazy loader that may return None
        viczo = main._get_viczo_brain()
    except Exception:
        viczo = None

    if viczo:
        try:
            viczo_resp = viczo.respond(text, base_response=resp, has_actions=bool(actions))
            if viczo_resp:
                resp = viczo_resp
        except Exception as e:
            print("Viczo.respond raised:", e)
            traceback.print_exc()

    print('\nFinal assistant response:', resp)
    # Use main._notify if present to exercise TTS path
    try:
        if hasattr(main, '_notify'):
            main._notify(resp)
        else:
            print('Assistant:', resp)
    except Exception as e:
        print('Error during notify:', e)
        traceback.print_exc()

except Exception as e:
    print('Error running interpret/respond:', e)
    traceback.print_exc()
    raise

print('\nOne-shot run complete')
