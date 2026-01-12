import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.assistant.spacy_nlu import interpret

test_cases = [
    ("open spotify", "open"),
    ("launch calculator", "open"),
    ("search for quantum physics", "search"),
    ("google python tutorials", "search"),
    ("volume up", "volume"),
    ("mute volume", "volume"),
    ("send message to mom saying hello", "whatsapp_send"),
    ("tell dad that I'll be late", "whatsapp_send"),
    ("sets volume to 50%", "volume"),
    ("search cats", "search"),
    ("open chrome", "open"),
    ("play shape of you", "play_song"),
    ("play believer on spotify", "play_song"),
    ("play some music", "play_song"),
    ("i want to hear shape of you", "play_song"),
    ("listen to mockingbird", "play_song"),
    ("stop song", "media_control"),
    ("pause music", "media_control"),
    ("next track", "media_control"),
    ("close spotify", "close_app"),
    ("exit chrome", "close_app"),
    ("kill notepad", "close_app"),
]

print("Running NLU Tests...")
passed = 0
failed = 0

for text, expected_type in test_cases:
    print(f"\nTesting: '{text}'")
    result = interpret(text)
    actions = result.get("actions", [])
    
    if not actions:
        print(f"FAILED: No actions returned for '{text}'")
        failed += 1
        continue
        
    action_type = actions[0].get("type")
    print(f" -> Result: {result.get('response')}")
    print(f" -> Action Type: {action_type}")
    
    if action_type == expected_type:
        print("PASSED")
        passed += 1
    else:
        print(f"FAILED: Expected {expected_type}, got {action_type}")
        failed += 1

print(f"\nSummary: {passed} Passed, {failed} Failed.")
