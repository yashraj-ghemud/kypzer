import re

def test_ai_compose_regex():
    text = "send info about Lenovo laptop to Dinesh with AI"
    
    # Regex copied from src/assistant/spacy_nlu.py
    pattern = r"(?i)(?:send|message|msg|draft)\s+(?:an?\s+)?(?:ai\s+)?(?:info|note|message|msg|details|summary)?\s*(?:about|on|regarding|for)?\s*(?P<topic>.+?)\s+(?:to|for)\s+(?P<contact>.+?)(?:\s+with\s+ai|\s+using\s+ai|\s+via\s+chatgpt|$)"
    
    print(f"Testing text: '{text}'")
    
    m = re.search(pattern, text)
    if m:
        topic = m.group("topic").strip()
        contact = m.group("contact").strip()
        
        # Extra cleaning logic present in the original code
        contact = re.sub(r"(?i)\s+(?:with|using|via)\s+(?:ai|gpt|chatgpt|openai)$", "", contact).strip()
        
        print(f"topic=\"{topic}\"")
        print(f"contact=\"{contact}\"")
        
        if topic == "Lenovo laptop" and contact == "Dinesh":
            print("Verification Check: PASSED")
        else:
            print("Verification Check: FAILED")
    else:
        print("No match found.")

if __name__ == "__main__":
    test_ai_compose_regex()
