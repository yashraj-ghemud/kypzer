try:
    import pyperclip
    print("Verified")
except ImportError:
    print("Failed to import pyperclip")
except Exception as e:
    print(f"An error occurred: {e}")
