import time
from src.assistant import tts as tts_mod
from src import main

# Set friendly persona
tts_mod.set_persona('friendly')

tests = [
    "Hi",
    "How are you?",
    "Open notepad",
    "volume chalu karo",
]

print("Starting quick interpret+TTS verification")
for text in tests:
    print('\n---')
    print("User:", text)
    plan = main.interpret(text)
    print("Interpret:", plan)
    resp = plan.get('response', '')
    if resp:
        print("Speaking response:", resp)
        try:
            # Use synchronous speak to make output ordering predictable
            tts_mod.speak(resp, emotion='friendly')
        except Exception as e:
            print("TTS speak error:", e)
    else:
        print("No response to speak")

    actions = plan.get('actions', [])
    if actions:
        for a in actions:
            print("Planned action:", a)
            # Simulate an action outcome being spoken
            try:
                outcome = a.get('type') + ' executed'
                tts_mod.speak(outcome, emotion='confident')
            except Exception as e:
                print("TTS outcome error:", e)

    # small pause between tests
    time.sleep(0.5)

print('\nVerification complete')
