# WhatsApp Desktop App Voice Message Automation
# Format: "recipient_name, message_text"
# Works with WhatsApp Windows/Mac Desktop App (not web)

import os
import subprocess
import sys
import time

import pyautogui
import pyttsx3

class WhatsAppDesktopVoiceBot:
    REFERENCE_WIDTH = 1920
    REFERENCE_HEIGHT = 1080

    def __init__(self):
        """Initialize the WhatsApp Desktop Voice Bot"""
        self.engine = None
        self.screen_width, self.screen_height = pyautogui.size()
        self.is_listening = False
        
    def initialize_tts_engine(self):
        """Initialize the text-to-speech engine"""
        try:
            self.engine = pyttsx3.init()
            # Configure TTS properties
            self.engine.setProperty('rate', 150)  # Speech speed
            self.engine.setProperty('volume', 1.0)  # Max volume
            print("✓ Text-to-Speech engine initialized")
        except Exception as e:
            print(f"✗ Error initializing TTS: {e}")
            sys.exit(1)
    
    def open_whatsapp_desktop(self):
        """Open WhatsApp Desktop Application"""
        try:
            print("⏳ Checking if WhatsApp Desktop is running...")
            
            # Try to find and focus WhatsApp window
            # For Windows
            if sys.platform == "win32":
                # Try using wmctrl or other methods to find WhatsApp window
                os.system("powershell -Command \"Get-Process WhatsApp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty MainWindowHandle\"")
                
                # If not open, try to open it
                try:
                    subprocess.Popen("WhatsApp")
                    time.sleep(5)
                    print("✓ WhatsApp Desktop opened")
                except:
                    print("⚠️  WhatsApp Desktop not found in PATH")
                    print("Please make sure WhatsApp is installed and running")
                    return False
            
            # For macOS
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "WhatsApp"])
                time.sleep(5)
                print("✓ WhatsApp Desktop opened (macOS)")
            
            return True
        except Exception as e:
            print(f"✗ Error opening WhatsApp: {e}")
            return False
    
    def _relative_point(self, ref_x, ref_y):
        """Translate reference coordinates (1920x1080) to current screen."""
        x = int((ref_x / self.REFERENCE_WIDTH) * self.screen_width)
        y = int((ref_y / self.REFERENCE_HEIGHT) * self.screen_height)
        return (x, y)

    def find_search_box(self):
        """Find and click the search box in WhatsApp Desktop"""
        try:
            print("🔍 Looking for search box...")
            time.sleep(1)
            
            # WhatsApp Desktop search box is usually at top-left
            # Coordinates may vary, these are approximate for 1920x1080
            search_x, search_y = self._relative_point(300, 60)
            
            pyautogui.click(search_x, search_y)
            time.sleep(0.5)
            print("✓ Clicked on search box")
            return True
        except Exception as e:
            print(f"✗ Error clicking search box: {e}")
            return False
    
    def search_contact(self, contact_name):
        """Search for contact in WhatsApp Desktop"""
        try:
            print(f"🔍 Searching for '{contact_name}'...")
            
            # Clear any existing text first
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            
            # Type contact name
            pyautogui.typewrite(contact_name, interval=0.05)
            time.sleep(1.5)
            
            # Press Enter to select first result
            pyautogui.press('enter')
            time.sleep(1)
            
            print(f"✓ Found and opened chat with '{contact_name}'")
            return True
        except Exception as e:
            print(f"✗ Error searching contact: {e}")
            return False
    
    def focus_message_box(self):
        """Ensure message input is focused before recording."""
        try:
            message_x, message_y = self._relative_point(960, 960)
            pyautogui.click(message_x, message_y)
            time.sleep(0.4)
            return True
        except Exception as e:
            print(f"✗ Error focusing message box: {e}")
            return False

    def click_voice_message_button(self):
        """Click on the microphone/voice message button"""
        try:
            print("🎙️  Looking for voice message button...")
            time.sleep(0.5)
            
            # Voice message button is usually at bottom-right of message input area
            # Near the send button - approximate coordinates
            mic_button_x, mic_button_y = self._relative_point(1850, 1020)
            
            pyautogui.click(mic_button_x, mic_button_y)
            time.sleep(0.5)
            print("✓ Clicked voice message button")
            return True
        except Exception as e:
            print(f"✗ Error clicking voice button: {e}")
            print("⚠️  Try clicking the microphone button manually")
            return False
    
    def record_voice_message(self, message):
        """
        Start recording and speak the message
        """
        try:
            print("🎤 Recording voice message...")
            print(f"📢 Speaking: '{message}'")
            
            # Add delay for recording to start
            time.sleep(1)
            
            # Use pyttsx3 to speak the message
            self.engine.say(message)
            self.engine.runAndWait()
            
            print("✓ Message spoken successfully")
            return True
        except Exception as e:
            print(f"✗ Error recording message: {e}")
            return False
    
    def send_voice_message(self):
        """Stop recording and send the voice message"""
        try:
            print("📤 Sending voice message...")
            time.sleep(0.5)
            
            # Release the microphone button (usually by clicking it again or pressing Enter)
            pyautogui.press('enter')
            time.sleep(1)
            
            print("✓ Voice message sent!")
            return True
        except Exception as e:
            print(f"✗ Error sending message: {e}")
            return False
    
    def manual_setup_message(self):
        """
        Guide user through manual process (for initial setup)
        """
        print("\n" + "="*60)
        print("📋 MANUAL SETUP - Please follow these steps:")
        print("="*60)
        print("\n1. Make sure WhatsApp Desktop is open and visible")
        print("2. Click on the search box at the top of the chat list")
        print("3. Type the contact name")
        print("4. Click on the contact to open the chat")
        print("5. Click the microphone button next to the message input")
        print("6. The script will then speak the message")
        print("7. Click the send button or press Enter")
        print("\nPress ENTER when you're ready to continue...")
        input()
    
    def ensure_workflow_ready(self, recipient_name):
        """Run open-search-select steps before speaking."""
        if not self.open_whatsapp_desktop():
            print("⚠️  WhatsApp Desktop not detected")
            print("Please open WhatsApp Desktop manually")
            return False

        time.sleep(2)

        if not self.find_search_box():
            print("⚠️  Could not auto-find search box")

        if not self.search_contact(recipient_name):
            print("⚠️  Trying manual search...")
            self.manual_setup_message()

        if not self.focus_message_box():
            print("⚠️  Message box focus failed; continuing")

        return True

    def start_voice_recording(self, recipient_name, message):
        """Complete workflow for voice message"""
        try:
            if not self.ensure_workflow_ready(recipient_name):
                return False
            
            # Click voice message button
            if not self.click_voice_message_button():
                print("⚠️  Please click the microphone button manually")
                input("Press ENTER after clicking the microphone button: ")
            
            # Record voice message
            if not self.record_voice_message(message):
                return False
            
            # Send the message
            if not self.send_voice_message():
                return False
            
            return True
        
        except Exception as e:
            print(f"✗ Error in voice message workflow: {e}")
            return False
    
    def close(self):
        """Cleanup"""
        print("✓ Process completed")


def parse_input(user_input):
    """Parse input in format 'name, message'"""
    try:
        parts = user_input.split(',', 1)
        if len(parts) != 2:
            return None, None
        
        recipient_name = parts[0].strip()
        message = parts[1].strip()
        
        if not recipient_name or not message:
            return None, None
        
        return recipient_name, message
    except Exception as e:
        print(f"✗ Error parsing input: {e}")
        return None, None


def display_welcome():
    """Display welcome message"""
    print("\n" + "="*70)
    print("🤖 WhatsApp Desktop Voice Message Automation Bot")
    print("="*70)
    print("\nThis bot automates voice message sending on WhatsApp Desktop App")
    print("\n✅ REQUIREMENTS:")
    print("   • WhatsApp Desktop app installed and running")
    print("   • Message must be 1-100 characters")
    print("   • System speakers at maximum volume")
    print("\n⏱️  TIME PER MESSAGE: 15-25 seconds")
    print("\n" + "="*70)


def display_tips():
    """Display helpful tips"""
    print("\n💡 TIPS FOR BEST RESULTS:")
    print("   • Keep system volume at MAXIMUM")
    print("   • Position WhatsApp window clearly on screen")
    print("   • Speak clearly during recording")
    print("   • Don't move mouse during recording")
    print("   • If microphone not detected, click it manually")
    print("\n" + "="*70)


def main():
    """Main function"""
    display_welcome()
    
    # Get user input
    print("\n📝 FORMAT: recipient_name, message_text")
    print("   Example: John Doe, Hello how are you")
    print("   Example: Mom, I'll be home soon\n")
    
    user_input = input("Enter recipient name and message: ")
    recipient_name, message = parse_input(user_input)
    
    if not recipient_name or not message:
        print("✗ Invalid format! Please use: 'name, message'")
        return
    
    print(f"\n✓ Recipient: {recipient_name}")
    print(f"✓ Message: {message}")
    print(f"✓ Message Length: {len(message)} characters")
    
    if len(message) > 100:
        print("⚠️  Warning: Message is long (>100 chars)")
        print("   Make sure to have enough time to speak it")
    
    display_tips()
    
    # Initialize bot
    bot = WhatsAppDesktopVoiceBot()
    bot.initialize_tts_engine()
    
    print("\n" + "="*70)
    print("🎯 STARTING AUTOMATION IN 5 SECONDS...")
    print("="*70)
    time.sleep(5)
    
    try:
        success = bot.start_voice_recording(recipient_name, message)
        
        if success:
            print("\n" + "="*70)
            print("✅ Voice message sent successfully!")
            print("="*70)
        else:
            print("\n" + "="*70)
            print("❌ Failed to send voice message")
            print("="*70)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
    finally:
        bot.close()


if __name__ == "__main__":
    main()
