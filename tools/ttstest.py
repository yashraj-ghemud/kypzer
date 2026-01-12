import sys, os
ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.assistant import tts

print('Available voices:')
voices = tts.list_voices()
for v in voices:
    print('-', v.get('name') or v.get('id'))

print('Current persona:', tts.get_persona())
print('Speaking test phrase...')
try:
    tts.speak('Hello Final Boss. This is a test of the speaking system.', emotion='friendly')
    print('speak() completed')
except Exception as e:
    print('speak() raised:', e)

print('Now testing speak_async...')
try:
    tts.speak_async('This is an asynchronous test. I hope you hear it.', emotion='friendly')
    print('speak_async() started')
except Exception as e:
    print('speak_async() raised:', e)

print('Done')
