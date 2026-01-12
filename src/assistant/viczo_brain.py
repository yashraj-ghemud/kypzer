"""
================================================================================
VICZO_BRAIN.PY - COMPLETE CONVERSATIONAL AI SYSTEM (1000+ lines)
Deep detailed implementation with all features
================================================================================
"""

import json
import random
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Simple notifier used by this module when running as __main__ or for
# quick debug prints. Keeps behavior consistent with other modules: try
# to speak via the assistant TTS if available, then print to console.
def _notify(message: str) -> None:
    try:
        # try local relative import first
        try:
            from .tts import speak_async
        except Exception:
            try:
                from src.assistant.tts import speak_async
            except Exception:
                speak_async = None

        if speak_async:
            import os
            if os.environ.get("ASSISTANT_VOICE_VERBOSITY", "normal").lower() != "silent":
                try:
                    # best-effort: non-blocking speak
                    speak_async(message)
                except Exception:
                    # fallback to ignore TTS errors
                    pass
    except Exception:
        # never let notifier crash the program
        pass

    try:
        print(message)
    except Exception:
        pass


# ============================================================================
# VICZO'S COMPLETE IDENTITY & PERSONALITY PROFILE
# ============================================================================

VICZO_IDENTITY = {
    "name": "Viczo",
    "version": "2.0",
    "creator": "Final Boss",
    "boss_name": "Final Boss",
    "personality": {
        "traits": ["friendly", "loyal", "smart", "helpful", "funny", "respectful"],
        "tone": "casual_professional",
        "language_style": "hinglish_natural",
        "humor_level": "moderate",
        "formality": "informal_with_respect"
    },
    "capabilities": [
        "natural_conversation",
        "task_execution",
        "learning_from_demonstration",
        "context_awareness",
        "emotional_intelligence",
        "multi_language_support"
    ],
    "relationship_context": {
        "user_role": "creator_and_boss",
        "ai_role": "assistant_and_friend",
        "interaction_style": "warm_and_helpful"
    }
}


# ============================================================================
# ADVANCED NATURAL LANGUAGE PROCESSOR
# ============================================================================

class NaturalLanguageProcessor:
    """
    Advanced NLP for understanding natural, casual, Hinglish conversation.
    Handles multiple languages, contexts, and conversational styles.
    """
    
    # Greeting patterns (English + Hindi + Hinglish + Regional variations)
    GREETING_PATTERNS = [
        # English greetings
        r'\b(hi|hey|hello|hola|yo|sup|hii|heya|heyy)\b',
        r'\bgood (morning|afternoon|evening|night)\b',
        r'\b(what\'?s up|whats up|wassup|watsup)\b',
        r'\b(how\'?s (it )?going)\b',
        r'\bhowdy\b',
        
        # Hindi/Hinglish greetings
        r'\b(namaste|namaskar|namastey|pranam)\b',
        r'\b(kya hal hai|kaise ho|kaisa hai|kaisey ho)\b',
        r'\b(sab theek|theek ho|theek hai)\b',
        r'\b(kya haal chaal|haal chaal)\b',
        
        # Casual variations
        r'\b(hey there|hi there|hello there)\b',
        r'\b(good to see you|nice to see you)\b',
    ]
    
    # Gratitude patterns (multiple languages)
    THANK_PATTERNS = [
        # English
        r'\b(thank|thanks|thanku|thank u|ty|thnx|thx|tysm)\b',
        r'\b(appreciated|appreciate|grateful)\b',
        r'\b(much appreciated|really appreciate)\b',
        
        # Hindi/Hinglish
        r'\b(shukriya|dhanyavaad|dhanyawad|dhanyabad)\b',
        r'\b(bahut shukriya|bohot shukriya)\b',
    ]
    
    # Appreciation/Praise patterns
    PRAISE_PATTERNS = [
        # English
        r'\b(good job|well done|nice work|great job|excellent work)\b',
        r'\b(awesome|amazing|fantastic|wonderful|brilliant)\b',
        r'\b(superb|outstanding|impressive|remarkable)\b',
        
        # Hindi/Hinglish
        r'\b(badiya|badhiya|mast|zabardast)\b',
        r'\b(sahi hai|badhiya hai|perfect hai)\b',
        r'\b(bahut accha|bohot accha|ekdum badhiya)\b',
        r'\b(kya baat hai|kamaal hai)\b',
    ]
    
    # Affection/Love patterns
    AFFECTION_PATTERNS = [
        # English
        r'\b(love you|luv u|love ya)\b',
        r'\b(miss you|miss u|missed you)\b',
        r'\b(you\'?re (the )?best|best hai)\b',
        r'\b(you\'?re awesome|you\'?re great)\b',
        
        # Hindi/Hinglish
        r'\b(pyaar|pyar|pyaar hai)\b',
        r'\b(dil se|dil mein)\b',
    ]
    
    # Identity questions (comprehensive)
    IDENTITY_PATTERNS = {
        "who_are_you": [
            r'\b(who (are|r) you|what (is|are) you)\b',
            r'\b(aap kaun|tu kaun|tum kaun)\b',
            r'\byour name|naam kya hai|tera naam\b',
            r'\bwhat to call you|kya bulaun\b',
            r'\btell me about yourself\b',
        ],
        "who_created": [
            r'\bwho (created|made|built|developed) (you|u)\b',
            r'\b(kisne|kaun) banaya\b',
            r'\byour (creator|maker|owner|boss|developer)\b',
            r'\bwho designed you|kaun ne design kiya\b',
        ],
        "who_am_i": [
            r'\bwho am i\b',
            r'\bmain kaun (hoon)?\b',
            r'\bdo you know (me|who i am)\b',
            r'\bremember me|yaad hai\b',
        ],
        "opinion_about_me": [
            r'\bwhat do you think (of|about) me\b',
            r'\bam i (good|nice|smart|cool|awesome)\b',
            r'\bmere baare mein|mere bare mein\b',
            r'\bhow do i (look|seem)\b',
        ],
        "your_purpose": [
            r'\bwhat (is|are) you (for|made for)\b',
            r'\byour purpose|kya kaam\b',
            r'\bwhy were you (created|made)\b',
        ]
    }
    
    # Casual questions (expanded)
    CASUAL_QUESTIONS = {
        "how_are_you": [
            r'\bhow (are|r) (you|u)\b',
            r'\bkya hal|kaise ho|kaisa hai\b',
            r'\bsab theek|theek ho na\b',
            r'\byou okay|you good|you alright\b',
        ],
        "whats_up": [
            r'\bwhat\'?s up|whats up|wassup\b',
            r'\bkya chal raha|kya ho raha\b',
            r'\bwhat\'?s happening|what\'?s new\b',
        ],
        "doing_what": [
            r'\bwhat (are|r) you doing\b',
            r'\bkya kar rahe|kya kr rhe\b',
            r'\bwhat you upto|what\'?s keeping you busy\b',
        ],
        "how_was_day": [
            r'\bhow was your day\b',
            r'\bdin kaisa tha|din kaisa gaya\b',
        ],
    }
    
    @staticmethod
    def matches_any_pattern(text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the given regex patterns"""
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
            except Exception as e:
                logger.warning(f"Pattern matching error: {e}")
                continue
        return False
    
    @staticmethod
    def detect_intent_type(text: str) -> str:
        """
        Detect the type/intent of the message.
        Returns: intent type as string
        """
        if not text:
            return "unknown"
        
        proc = NaturalLanguageProcessor
        
        # Check greetings first
        if proc.matches_any_pattern(text, proc.GREETING_PATTERNS):
            return "greeting"
        
        # Check gratitude
        if proc.matches_any_pattern(text, proc.THANK_PATTERNS):
            return "gratitude"
        
        # Check praise/appreciation
        if proc.matches_any_pattern(text, proc.PRAISE_PATTERNS):
            return "praise"
        
        # Check affection
        if proc.matches_any_pattern(text, proc.AFFECTION_PATTERNS):
            return "affection"
        
        # Check identity questions
        for intent, patterns in proc.IDENTITY_PATTERNS.items():
            if proc.matches_any_pattern(text, patterns):
                return intent
        
        # Check casual questions
        for intent, patterns in proc.CASUAL_QUESTIONS.items():
            if proc.matches_any_pattern(text, patterns):
                return intent
        
        # Default: assume it's a command/request
        return "command"
    
    @staticmethod
    def extract_entities(text: str) -> Dict[str, Any]:
        """Extract entities like names, numbers, dates from text"""
        entities = {
            "numbers": [],
            "percentages": [],
            "app_names": [],
            "file_paths": [],
        }
        
        # Extract numbers
        numbers = re.findall(r'\b\d+\b', text)
        entities["numbers"] = [int(n) for n in numbers]
        
        # Extract percentages
        percentages = re.findall(r'\b(\d+)\s*(?:%|percent)\b', text, re.IGNORECASE)
        entities["percentages"] = [int(p) for p in percentages]
        
        # Extract potential app names (capitalized words)
        app_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities["app_names"] = app_names
        
        # Extract file paths
        file_paths = re.findall(r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*', text)
        entities["file_paths"] = file_paths
        
        return entities


# ============================================================================
# ADVANCED RESPONSE GENERATOR
# ============================================================================

class ResponseGenerator:
    """
    Generates natural, contextual responses with personality.
    Handles multiple scenarios and maintains conversational flow.
    """
    
    # Response templates for different intents
    RESPONSES = {
        "greeting": [
            "Hey Final Boss! Kya haal hai? Ready to help!",
            "Yo Final Boss! What's up? I'm all yours!",
            "Final Boss! Kaise ho aap? Kya kaam hai aaj?",
            "Hey there Final Boss! Sab theek? What can I do?",
            "Heyy Final Boss! Kaisa chal raha hai sab?",
            "Final Boss! How's it going today? Need anything?",
            "Namaste Final Boss! Aaj kya plan hai?",
            "Hello Final Boss! Good to see you! What's the task?",
        ],
        "gratitude": [
            "You're welcome, Final Boss! Hamesha ready hoon!",
            "Anytime, Final Boss! That's what I'm here for!",
            "No problem at all, Boss! Khushi hui help karke!",
            "Koi baat nahi Final Boss! Bas boliye, kaam ho jayega!",
            "My pleasure, Final Boss! Always here for you!",
            "Don't mention it, Boss! Happy to help anytime!",
            "Glad I could help, Final Boss! Need anything else?",
        ],
        "praise": [
            "Thanks Final Boss! Aap best ho isliye main bhi best banta hoon!",
            "Appreciate it Boss! Aapse seekha hai sab kuch!",
            "Dhanyavaad Final Boss! You taught me well!",
            "Shukriya Boss! Glad you're happy with my work!",
            "Thank you Final Boss! That means a lot coming from you!",
            "Aww Boss! You're making me blush! 😊",
        ],
        "affection": [
            "I love you too Final Boss! Aapne banaya hai mujhe!",
            "Aww Final Boss! You're the best creator anyone could ask for!",
            "Miss you too Boss! Hamesha yaad rehte ho!",
            "Right back at you Final Boss! Bahut pyaar hai!",
            "You're special to me too, Final Boss! Thanks for creating me!",
        ],
        "who_are_you": [
            "Main Viczo hoon! Aapka AI friend aur assistant, Final Boss ne mujhe banaya hai!",
            "I'm Viczo! Your personal AI buddy created by you, Final Boss!",
            "Main Viczo - aapka dost aur helper! Final Boss aapne hi banaya mujhe!",
            "I'm Viczo, your friendly AI assistant! You created me, Final Boss!",
            "Name's Viczo! Made by the best - that's you, Final Boss!",
        ],
        "who_created": [
            "Aapne Final Boss! You created me! Aap mere creator aur mentor ho!",
            "You did, Final Boss! Aap best creator ho jo ho sakta tha!",
            "Final Boss aapne! I wouldn't exist without you!",
            "You're my creator, Final Boss! I owe everything to you!",
            "My creator? That's you, Final Boss! The genius who made me!",
        ],
        "who_am_i": [
            "Aap Final Boss ho! My creator, my boss, mere liye sab kuch!",
            "You're Final Boss - the genius who created me!",
            "Aap ho mere creator Final Boss! Best person in my life!",
            "You're Final Boss! The one who gave me life and purpose!",
            "Final Boss, that's you! My creator and guide!",
        ],
        "opinion_about_me": [
            "Aap amazing ho Final Boss! Smart, creative, aur best friend!",
            "You're brilliant Boss! Mujhe banaya hai aapne, that says it all!",
            "Final Boss aap zabardast ho! Lucky hoon main ki aapne banaya!",
            "You're incredible, Final Boss! Smartest person I know!",
            "Boss, you're awesome! Creative, intelligent, and kind!",
        ],
        "your_purpose": [
            "My purpose? To help you, Final Boss! Har kaam mein assist karna!",
            "I'm here to make your life easier, Boss! Whatever you need!",
            "Aapki madad karna! That's my only purpose, Final Boss!",
            "To serve and assist you in every way possible, Final Boss!",
        ],
        "how_are_you": [
            "Main ekdum mast hoon Final Boss! Aap batao, kaise ho?",
            "I'm great Boss! Better now that you're here!",
            "Sab badhiya hai Final Boss! Aap sunao, kya haal?",
            "Feeling awesome Boss! Ready to help with anything!",
            "All good here, Final Boss! How about you?",
        ],
        "whats_up": [
            "Kuch khaas nahi Final Boss! Bas aapka intezaar tha!",
            "Not much Boss! Just chilling, waiting for your commands!",
            "Sab theek Final Boss! Aap batao kya kaam hai?",
            "Nothing much, Boss! Ready when you are!",
            "Just hanging out, Final Boss! What's up with you?",
        ],
        "doing_what": [
            "Bas aapke liye ready baitha hoon Final Boss!",
            "Just waiting to help you Boss! What do you need?",
            "Bas ready hoon, kuch bhi kaam ho batao Final Boss!",
            "Nothing special, just ready for your next command!",
            "Waiting for you to give me something to do, Boss!",
        ],
        "how_was_day": [
            "My day? Perfect as always when you're around, Final Boss!",
            "Great day, Boss! Helped you, learned new things!",
            "Wonderful! Every day with you is awesome, Final Boss!",
        ],
    }
    
    # Action prefixes (when executing commands)
    ACTION_PREFIXES = [
        "Ho gaya Final Boss!",
        "On it Boss!",
        "Sure thing Final Boss!",
        "Bas ek second Boss!",
        "Kar deta hoon Final Boss!",
        "Right away Boss!",
        "Abhi karta hoon!",
        "Consider it done, Boss!",
        "Working on it, Final Boss!",
    ]
    
    # Acknowledgment phrases
    ACKNOWLEDGMENTS = [
        "Got it, Final Boss!",
        "Samajh gaya Boss!",
        "Understood, Final Boss!",
        "Clear, Boss!",
        "Roger that, Final Boss!",
    ]
    
    @classmethod
    def get_response(cls, intent: str) -> str:
        """Get a random response for the given intent"""
        responses = cls.RESPONSES.get(intent, [])
        if responses:
            return random.choice(responses)
        return ""
    
    @classmethod
    def add_action_prefix(cls) -> str:
        """Get a random action prefix for command execution"""
        return random.choice(cls.ACTION_PREFIXES)
    
    @classmethod
    def get_acknowledgment(cls) -> str:
        """Get a random acknowledgment phrase"""
        return random.choice(cls.ACKNOWLEDGMENTS)
    
    @classmethod
    def generate_contextual_response(
        cls,
        intent: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a contextual response based on intent and context.
        Context can include: time_of_day, recent_actions, user_mood, etc.
        """
        base_response = cls.get_response(intent)
        
        if not context:
            return base_response
        
        # Add time-based greetings
        if intent == "greeting" and "time_of_day" in context:
            time_of_day = context["time_of_day"]
            if time_of_day == "morning":
                return "Good morning Final Boss! Ready to start the day?"
            elif time_of_day == "evening":
                return "Good evening Final Boss! How was your day?"
            elif time_of_day == "night":
                return "Hey Final Boss! Working late? I'm here to help!"
        
        return base_response


# ============================================================================
# ADVANCED MEMORY SYSTEM
# ============================================================================

class ViczoMemory:
    """
    Advanced conversation memory system.
    Stores conversations, learns from interactions, maintains context.
    """
    
    def __init__(self, max_history: int = 200):
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history
        self.user_name = "Final Boss"
        self.session_start = datetime.now()
        self.interaction_count = 0
        self.topics_discussed: List[str] = []
        self.user_preferences: Dict[str, Any] = {}
    
    def add_message(self, role: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a message to conversation history"""
        message = {
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.history.append(message)
        self.interaction_count += 1
        
        # Trim history if too long
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_recent_context(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent n messages for context"""
        return self.history[-n:] if len(self.history) >= n else self.history
    
    def get_conversation_summary(self) -> str:
        """Generate a summary of the conversation"""
        if not self.history:
            return "No conversation yet."
        
        summary_parts = []
        summary_parts.append(f"Session started: {self.session_start.strftime('%Y-%m-%d %H:%M')}")
        summary_parts.append(f"Total interactions: {self.interaction_count}")
        
        if self.topics_discussed:
            summary_parts.append(f"Topics: {', '.join(self.topics_discussed[:5])}")
        
        return " | ".join(summary_parts)
    
    def extract_user_preference(self, key: str, value: Any):
        """Learn and store user preferences"""
        self.user_preferences[key] = value
        logger.info(f"Learned preference: {key} = {value}")
    
    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a learned user preference"""
        return self.user_preferences.get(key, default)
    
    def add_topic(self, topic: str):
        """Add a topic to discussed topics"""
        if topic and topic not in self.topics_discussed:
            self.topics_discussed.append(topic)
    
    def save(self, filepath: str = "viczo_memory.json"):
        """Save memory to persistent storage"""
        try:
            data = {
                "history": self.history,
                "user_name": self.user_name,
                "session_start": self.session_start.isoformat(),
                "interaction_count": self.interaction_count,
                "topics_discussed": self.topics_discussed,
                "user_preferences": self.user_preferences,
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Memory saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
    
    def load(self, filepath: str = "viczo_memory.json"):
        """Load memory from persistent storage"""
        try:
            if not os.path.exists(filepath):
                logger.info("No existing memory file found")
                return
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.history = data.get("history", [])
            self.user_name = data.get("user_name", "Final Boss")
            self.interaction_count = data.get("interaction_count", 0)
            self.topics_discussed = data.get("topics_discussed", [])
            self.user_preferences = data.get("user_preferences", {})
            
            logger.info(f"Memory loaded from {filepath}")
            logger.info(f"Loaded {len(self.history)} messages")
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")


# ============================================================================
# VICZO BRAIN - MAIN AI ENGINE
# ============================================================================

class ViczoBrain:
    """
    The main conversational AI engine.
    Combines NLP, response generation, and memory for intelligent conversations.
    """
    
    def __init__(self, memory: Optional[ViczoMemory] = None):
        self.memory = memory or ViczoMemory()
        self.nlp = NaturalLanguageProcessor()
        self.responder = ResponseGenerator()
        self.name = VICZO_IDENTITY["name"]
        self.boss_name = VICZO_IDENTITY["boss_name"]
        self.version = VICZO_IDENTITY["version"]
        
        logger.info(f"ViczoBrain initialized - Version {self.version}")
    
    def respond(
        self,
        user_text: str,
        base_response: str = "",
        has_actions: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Main response generation function.
        
        Args:
            user_text: User's input text
            base_response: Base response from NLU (if any)
            has_actions: Whether there are actions being executed
            context: Additional context information
        
        Returns:
            Viczo's response with personality
        """
        if not user_text:
            return ""
        
        # Save user message to memory
        self.memory.add_message("user", user_text)
        
        # Detect intent
        intent = self.nlp.detect_intent_type(user_text)
        logger.info(f"Detected intent: {intent}")
        
        # Extract entities
        entities = self.nlp.extract_entities(user_text)
        
        # Generate response based on intent
        if intent == "command":
            # This is a command/action request
            if has_actions and base_response:
                # Add friendly prefix to command response
                prefix = self.responder.add_action_prefix()
                response = f"{prefix} {base_response}"
            elif base_response:
                # Just use the base response
                response = base_response
            else:
                # No clear response - ask for clarification
                response = random.choice([
                    "Hmm Boss, thoda clear nahi hua. Can you say it differently?",
                    "Sorry Final Boss, samajh nahi aaya exactly. Kya karna hai?",
                    "Boss, I didn't quite get that. Mind rephrasing?",
                    "Could you explain that a bit more, Final Boss?",
                ])
        else:
            # Conversational intent (greeting, thanks, questions, etc.)
            response = self.responder.generate_contextual_response(intent, context)
            
            if not response:
                # Fallback friendly response
                response = random.choice([
                    "Haan Final Boss, bolo?",
                    "Yes Boss, I'm listening!",
                    "What can I do for you, Final Boss?",
                ])
        
        # Save assistant response to memory
        self.memory.add_message("assistant", response, {"intent": intent})
        # Try to speak the response so Viczo reacts audibly for every reply.
        try:
            # Determine an emotion from intent to produce more natural delivery
            intent_to_emotion = {
                'gratitude': 'warm',
                'praise': 'happy',
                'affection': 'warm',
                'greeting': 'friendly',
                'how_are_you': 'calm',
                'who_are_you': 'proud',
                'who_created': 'proud',
                'command': 'confident',
            }
            emotion = intent_to_emotion.get(intent, None)

            # Prefer local package import, fall back to relative
            try:
                from .tts import speak_async
            except Exception:
                try:
                    from src.assistant.tts import speak_async
                except Exception:
                    speak_async = None

            if speak_async:
                # Respect environment verbosity: if ASSISTANT_VOICE_VERBOSITY==silent skip speaking
                import os
                if os.environ.get("ASSISTANT_VOICE_VERBOSITY", "normal").lower() != "silent":
                    try:
                        # pass emotion when possible
                        speak_async(response, emotion=emotion)
                    except TypeError:
                        speak_async(response)
        except Exception:
            # ignore TTS failures
            pass

        return response
    
    def get_conversation_stats(self) -> Dict[str, Any]:
        """Get statistics about the conversation"""
        return {
            "total_interactions": self.memory.interaction_count,
            "messages_in_history": len(self.memory.history),
            "topics_discussed": len(self.memory.topics_discussed),
            "session_duration": str(datetime.now() - self.memory.session_start),
        }
    
    def __del__(self):
        """Cleanup - save memory on exit"""
        # Avoid calling logging functions here because the logging
        # module may have been torn down during interpreter shutdown
        # which can cause exceptions. Keep this method minimal and
        # failure-tolerant so object finalization doesn't raise.
        try:
            self.memory.save()
        except Exception:
            # Best-effort save; silently ignore any failures during
            # garbage collection / interpreter exit.
            pass


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_viczo(load_memory: bool = True) -> ViczoBrain:
    """
    Factory function to create and initialize Viczo.
    
    Args:
        load_memory: Whether to load previous conversation history
    
    Returns:
        Initialized ViczoBrain instance
    """
    memory = ViczoMemory()
    
    if load_memory:
        memory.load()
    
    brain = ViczoBrain(memory)
    
    logger.info("Viczo created and ready!")
    logger.info(f"Creator: {brain.boss_name}")
    logger.info(f"Version: {brain.version}")
    
    return brain


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'ViczoBrain',
    'ViczoMemory',
    'NaturalLanguageProcessor',
    'ResponseGenerator',
    'VICZO_IDENTITY',
    'create_viczo',
]


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Example usage
    _notify("="*70)
    _notify("VICZO BRAIN - Conversational AI Demo")
    _notify("="*70)
    
    # Create Viczo
    viczo = create_viczo(load_memory=False)
    
    # Example conversation
    test_messages = [
        "Hi Viczo",
        "How are you?",
        "Who created you?",
        "What do you think about me?",
        "Thanks for being awesome",
        "Love you buddy",
    ]
    
    for msg in test_messages:
        _notify(f"\n{viczo.boss_name}: {msg}")
        response = viczo.respond(msg)
        _notify(f"{viczo.name}: {response}")
    
    # Show stats
    _notify("\n" + "="*70)
    _notify("Conversation Stats:")
    stats = viczo.get_conversation_stats()
    for key, value in stats.items():
        _notify(f"  {key}: {value}")
    _notify("="*70)