import spacy
from spacy.matcher import Matcher
from typing import Dict, Any, List, Optional
import re

class SpacyNLU:
    def __init__(self, model_name: str = "en_core_web_sm"):
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            print(f"Model '{model_name}' not found. Downloading...")
            from spacy.cli import download
            download(model_name)
            self.nlp = spacy.load(model_name)

        self.matcher = Matcher(self.nlp.vocab)
        self._add_patterns()

    def _add_patterns(self):
        # Open App
        # Patterns: "open spotify", "launch calculator", "start notepad"
        open_patterns = [
            [{"LOWER": {"IN": ["open", "launch", "start", "run"]}}, {"OP": "+"}],
        ]
        self.matcher.add("OPEN_APP", open_patterns)

        # Search
        # Patterns: "search for x", "google x", "search x"
        search_patterns = [
            [{"LOWER": {"IN": ["search", "google", "find"]}}, {"LOWER": "for", "OP": "?"}, {"OP": "+"}],
        ]
        self.matcher.add("SEARCH", search_patterns)

        # System Controls
        # Volume
        volume_patterns = [
            [{"LOWER": "volume"}, {"LOWER": {"IN": ["up", "down", "max", "mute", "unmute"]}}],
            [{"LOWER": {"IN": ["mute", "unmute"]}}],
            [{"LEMMA": "set"}, {"LOWER": "volume"}, {"LOWER": "to"}, {"LIKE_NUM": True}, {"LOWER": "%", "OP": "?"}],
            [{"LEMMA": "set"}, {"LOWER": "volume"}, {"LIKE_NUM": True}, {"LOWER": "%", "OP": "?"}],
        ]
        self.matcher.add("VOLUME_CONTROL", volume_patterns)

        # WhatsApp
        # Patterns: "send message to x", "tell x that y"
        whatsapp_patterns = [
            [{"LOWER": "send"}, {"LOWER": "message"}, {"LOWER": "to"}, {"OP": "+"}],
            [{"LOWER": "tell"}, {"OP": "+"}, {"LOWER": "that"}, {"OP": "+"}],
            [{"LOWER": "whatsapp"}, {"OP": "+"}], 
        ]
        self.matcher.add("WHATSAPP", whatsapp_patterns)

        # Music
        # Patterns: 
        # "play x", "play x on spotify"
        # "I want to hear x", "listen to x"
        music_patterns = [
            [{"LOWER": "play"}, {"OP": "+"}],
            [{"LOWER": "hear"}, {"OP": "+"}],
            [{"LOWER": "listen"}, {"LOWER": "to", "OP": "?"}, {"OP": "+"}],
            [{"LOWER": "want"}, {"LOWER": "to"}, {"LOWER": {"IN": ["hear", "listen", "play"]}}, {"LOWER": "to", "OP": "?"}, {"OP": "+"}],
        ]
        self.matcher.add("PLAY_MUSIC", music_patterns)

        # Media Control (Stop/Pause/Next)
        media_patterns = [
            [{"LOWER": {"IN": ["stop", "pause", "resume"]}}, {"LOWER": {"IN": ["song", "music", "playback", "playing", "media"]}, "OP": "?"}],
            [{"LOWER": {"IN": ["next", "skip"]}}, {"LOWER": {"IN": ["song", "track"]}, "OP": "?"}],
            [{"LOWER": {"IN": ["previous", "back"]}}, {"LOWER": {"IN": ["song", "track"]}, "OP": "?"}],
        ]
        self.matcher.add("MEDIA_CONTROL", media_patterns)

        # Close App
        # Patterns: "close spotify", "exit chrome", "kill notepad"
        close_app_patterns = [
            [{"LOWER": {"IN": ["close", "exit", "kill", "terminate", "quit", "end", "stop"]}}, {"OP": "+"}],
        ]
        self.matcher.add("CLOSE_APP", close_app_patterns)
        
        # Greeting
        greeting_patterns = [
            [{"LOWER": {"IN": ["hi", "hello", "hey", "greetings", "buddy"]}}],
            [{"LOWER": {"IN": ["good", "morning", "afternoon", "evening"]}}, {"LOWER": {"IN": ["morning", "afternoon", "evening"]}}],
        ]
        self.matcher.add("GREETING", greeting_patterns)

        # AI Compose (WhatsApp/Notepad)
        # Patterns: "with ai", "using ai", "ask chatgpt", "via chatgpt"
        ai_patterns = [
            [{"LOWER": {"IN": ["with", "using", "via", "ask"]}}, {"LOWER": {"IN": ["ai", "gpt", "chatgpt", "openai"]}}],
            [{"LOWER": {"IN": ["ai", "chatgpt", "gpt"]}}, {"LOWER": {"IN": ["help", "compose", "write", "draft"]}}],
        ]
        self.matcher.add("AI_COMPOSE", ai_patterns)
    
    def parse(self, text: str) -> Dict[str, Any]:
        doc = self.nlp(text)
        matches = self.matcher(doc)
        
        # Sort matches by length (longest match first) to prefer more specific patterns
        matches.sort(key=lambda x: x[2] - x[1], reverse=True)

        if not matches:
            return {"response": "I didn't quite catch that.", "actions": []}

        match_id, start, end = matches[0]
        string_id = self.nlp.vocab.strings[match_id]
        span = doc[start:end]

        if string_id == "GREETING":
            return {"response": "Hello Final Boss! How can I help you today?", "actions": []}

        if string_id == "AI_COMPOSE":
            # Extract topic and contact for "send info about X to Y with AI"
            # This is a complex intent, so we use regex heuristics on the full text
            # to robustly capture the slots.
            
            # Pattern 1: Send [topic] to [contact] ...
            m = re.search(r"(?i)(?:send|message|msg|draft)\s+(?:an?\s+)?(?:ai\s+)?(?:info|note|message|msg|details|summary)?\s*(?:about|on|regarding|for)?\s*(?P<topic>.+?)\s+(?:to|for)\s+(?P<contact>.+?)(?:\s+with\s+ai|\s+using\s+ai|\s+via\s+chatgpt|$)", text)
            if m:
                topic = m.group("topic").strip()
                contact = m.group("contact").strip()
                # Clean trailing "with ai" from contact if regex grabbed it
                contact = re.sub(r"(?i)\s+(?:with|using|via)\s+(?:ai|gpt|chatgpt|openai)$", "", contact).strip()
                
                return {
                    "response": f"Drafting AI message on '{topic}' for {contact}.",
                    "actions": [{
                        "type": "whatsapp_ai_compose_send",
                        "parameters": {
                            "topic": topic,
                            "contact": contact,
                            "topic_raw": topic
                        }
                    }]
                }
            
            # Fallback Pattern 2: just topic "write about X with AI" (assumes notepad or generic)
            m_topic = re.search(r"(?i)(?:about|on|regarding)\s+(?P<topic>.+?)(?:\s+with\s+ai|\s+using\s+ai|$)", text)
            topic = m_topic.group("topic").strip() if m_topic else "that topic"
            return {
                "response": f"Writing about {topic} with AI.",
                "actions": [{"type": "whatsapp_ai_compose_send", "parameters": {"topic": topic, "contact": "Notes"}}]
            }

        if string_id == "OPEN_APP":
            # Extract app name. Usually it's everything after the trigger word.
            # Trigger words: open, launch, start, run
            app_name = text[span[1].idx:].strip()
            return {
                "response": f"Opening {app_name}.",
                "actions": [{"type": "open", "parameters": {"path": app_name}}]
            }

        elif string_id == "SEARCH":
            # Extract query
            # "search for cats" -> "cats"
            # "google python" -> "python"
            query = text[span[0].idx + len(span[0].text):].strip()
            # Remove "for" if present at start
            if query.lower().startswith("for "):
                query = query[4:].strip()
            
            return {
                "response": f"Searching for {query}.",
                "actions": [{"type": "search", "parameters": {"query": query}}]
            }

        elif string_id == "VOLUME_CONTROL":
            # Determine action
            lower_text = text.lower()
            if "mute" in lower_text:
                return {
                    "response": "Muting volume.",
                    "actions": [{"type": "volume", "parameters": {"mute": True}}]
                }
            elif "unmute" in lower_text:
               return {
                    "response": "Unmuting volume.",
                    "actions": [{"type": "volume", "parameters": {"mute": False}}]
                }
            elif "up" in lower_text:
                return {
                    "response": "Turning volume up.",
                    "actions": [{"type": "volume", "parameters": {"delta": 10}}]
                }
            elif "down" in lower_text:
                return {
                    "response": "Turning volume down.",
                    "actions": [{"type": "volume", "parameters": {"delta": -10}}]
                }
            elif "set" in lower_text:
                # Extract number
                nums = [token.text for token in doc if token.like_num]
                if nums:
                    level = int(nums[0])
                    return {
                        "response": f"Setting volume to {level}%.",
                        "actions": [{"type": "volume", "parameters": {"level": level}}]
                    }

        elif string_id == "WHATSAPP":
            # Very basic extraction for now
            # "send message to mom saying hello"
            # "tell mom that I am late"
            
            contact = ""
            message = ""
            
            lower_text = text.lower()
            if "send message to" in lower_text:
                parts = re.split(" to ", text, flags=re.IGNORECASE, maxsplit=1)
                if len(parts) > 1:
                    remainder = parts[1]
                    # Split contact and message
                    if " saying " in remainder:
                        contact, message = re.split(" saying ", remainder, flags=re.IGNORECASE, maxsplit=1)
                    elif " that " in remainder: # less common for "send message" but possible
                         contact, message = re.split(" that ", remainder, flags=re.IGNORECASE, maxsplit=1)
                    else:
                        contact = remainder # Message might be missing, or just opening chat
                        
            elif "tell" in lower_text:
                # "tell mom that..."
                parts = re.split("tell ", text, flags=re.IGNORECASE, maxsplit=1)
                if len(parts) > 1:
                    remainder = parts[1]
                    if " that " in remainder:
                        contact, message = re.split(" that ", remainder, flags=re.IGNORECASE, maxsplit=1)
                    else:
                        contact = remainder # likely incomplete

            if contact:
                contact = contact.strip()
                message = message.strip()
                return {
                    "response": f"Sending WhatsApp message to {contact}.",
                    "actions": [{"type": "whatsapp_send", "parameters": {"contact": contact, "message": message}}]
                }

        elif string_id == "PLAY_MUSIC":
            # Strategies to extract song name based on matched pattern length/content
            # "play shape of you" -> "shape of you"
            # "i want to hear shape of you" -> "shape of you"
            
            raw_query = text[span[0].idx + len(span[0].text):].strip() # Default fallback: everything after first token
            
            # Refine based on known prefixes
            lower_text = text.lower()
            prefixes = [
                "i want to hear", "i want to listen to", "i want to play", 
                "play", "hear", "listen to"
            ]
            
            # Find the longest matching prefix
            longest_prefix = ""
            for p in prefixes:
                if lower_text.startswith(p) and len(p) > len(longest_prefix):
                    longest_prefix = p
            
            if longest_prefix:
                raw_query = text[len(longest_prefix):].strip()

            # Remove "on spotify" suffix matches
            song = re.sub(r"(?i)\s+on\s+spotify$", "", raw_query)
            song = song.strip()
            
            if not song:
                return {"response": "What should I play?", "actions": []}

            return {
                "response": f"Playing {song} on Spotify.",
                "actions": [{"type": "play_song", "parameters": {"song": song}}]
            }

            return {
                "response": f"Playing {song} on Spotify.",
                "actions": [{"type": "play_song", "parameters": {"song": song}}]
            }

        elif string_id == "MEDIA_CONTROL":
            lower_text = text.lower()
            if any(w in lower_text for w in ["stop", "pause"]):
                # Determine if it's stop or pause explicitly? 
                # Usuaally 'stop' media key stops, 'playpause' toggles.
                # If user says "stop", we might want strict stop or playpause. 
                # Let's map 'stop' to stop, 'pause' to play_pause (toggle).
                if "stop" in lower_text:
                     return {
                        "response": "Stopping playback.",
                        "actions": [{"type": "media_control", "parameters": {"command": "stop"}}]
                    }
                else:
                    return {
                        "response": "Pausing music.",
                        "actions": [{"type": "media_control", "parameters": {"command": "play_pause"}}]
                    }
            elif "resume" in lower_text:
                 return {
                    "response": "Resuming music.",
                    "actions": [{"type": "media_control", "parameters": {"command": "play_pause"}}]
                }
            elif "next" in lower_text or "skip" in lower_text:
                 return {
                    "response": "Skipping to next song.",
                    "actions": [{"type": "media_control", "parameters": {"command": "next"}}]
                }
            elif "previous" in lower_text or "back" in lower_text:
                 return {
                    "response": "Going back to previous song.",
                    "actions": [{"type": "media_control", "parameters": {"command": "prev"}}]
                }



        elif string_id == "CLOSE_APP":
            # Extract app name. "close [app name]"
            # Remove the trigger word (close/exit/kill)
            trigger_words = {"close", "exit", "kill", "terminate", "quit"}
            words = text.split()
            if words and words[0].lower() in trigger_words:
                app_name = " ".join(words[1:]).strip()
            else:
                # Fallback: extract from span if complex structure, though regex above is simple
                app_name = text[span[1].idx:].strip()
            
            if app_name:
                return {
                    "response": f"Closing {app_name}.",
                    "actions": [{"type": "close_app", "parameters": {"name": app_name}}]
                }

        return {"response": "I understood the intent but couldn't parse the details.", "actions": []}

# Singleton instance to be used
_nlu_instance = None

def get_nlu():
    global _nlu_instance
    if _nlu_instance is None:
        _nlu_instance = SpacyNLU()
    return _nlu_instance

def interpret(text: str) -> Dict[str, Any]:
    nlu = get_nlu()
    return nlu.parse(text)
