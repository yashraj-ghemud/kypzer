import sys
import traceback

print("Attempting to import execute_action from src.assistant.actions...")

try:
    from src.assistant.actions import execute_action
    print("Successfully imported execute_action.")
except Exception:
    print("Failed to import execute_action.")
    print(traceback.format_exc())
