
import sys
import os
import traceback

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("Attempting to import pycaw...")
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    print("Pycaw imported successfully.")
except Exception:
    print("Failed to import pycaw:")
    traceback.print_exc()
    sys.exit(1)

print("\nAttempting to set volume...")
try:
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    from ctypes import POINTER, cast
    volume = cast(POINTER(IAudioEndpointVolume), interface)
    
    current = volume.GetMasterVolumeLevelScalar()
    print(f"Current volume: {current * 100:.2f}%")
    
    # Try setting to same volume to test
    volume.SetMasterVolumeLevelScalar(current, None)
    print("Successfully set volume (no change).")
    
except Exception:
    print("Failed to set volume:")
    traceback.print_exc()
