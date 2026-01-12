import os
import sys
import zipfile
import shutil
import urllib.request

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = os.path.join(os.getcwd(), "models")
VOSK_DIR = os.path.join(MODEL_DIR, "vosk")
ZIP_PATH = os.path.join(MODEL_DIR, "model.zip")

def setup_vosk():
    print(f"Checking Vosk model configuration...")
    
    if os.path.exists(VOSK_DIR) and os.path.isdir(VOSK_DIR):
        # Check if it looks populated
        if os.path.exists(os.path.join(VOSK_DIR, "conf")):
            print(f"✅ Vosk model already present at: {VOSK_DIR}")
            return

    print(f"⚠️ Vosk model missing. Downloading small English model...")
    print(f"URL: {MODEL_URL}")
    
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Download
    try:
        print("Downloading... (this may take a moment)")
        urllib.request.urlretrieve(MODEL_URL, ZIP_PATH)
        print("Download complete.")
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        sys.exit(1)

    # Extract
    try:
        print("Extracting...")
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            zip_ref.extractall(MODEL_DIR)
        print("Extraction complete.")
        
        # Renaissance move: Rename the extracted folder (vosk-model-small-en-us-0.15) to 'vosk'
        extracted_name = "vosk-model-small-en-us-0.15"
        extracted_path = os.path.join(MODEL_DIR, extracted_name)
        
        if os.path.exists(VOSK_DIR):
            shutil.rmtree(VOSK_DIR)
            
        if os.path.exists(extracted_path):
            os.rename(extracted_path, VOSK_DIR)
            print(f"✅ Model installed to: {VOSK_DIR}")
        else:
            print(f"❌ Could not find extracted folder: {extracted_path}")
            # Check what was extracted
            print("Contents of models folder:", os.listdir(MODEL_DIR))
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Failed to extract model: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(ZIP_PATH):
            os.remove(ZIP_PATH)

if __name__ == "__main__":
    setup_vosk()
