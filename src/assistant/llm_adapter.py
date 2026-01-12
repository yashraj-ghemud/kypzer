import google.generativeai as genai
import os
import json
import re
from typing import Any, Dict, Optional, List
from .config import settings
from .conversation import ConversationMemory

_GenAI_Configured = False

def _configure_genai():
    global _GenAI_Configured
    if _GenAI_Configured:
        return True
    
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return False
        
    try:
        genai.configure(api_key=api_key)
        _GenAI_Configured = True
        return True
    except Exception:
        return False

def llm_plan(user_text: str, memory: Optional[ConversationMemory] = None) -> Dict[str, Any]:
    """
    Generate a response and action plan using Gemini (if available).
    Returns a dict with 'response' (str) and 'actions' (list).
    """
    # 1. Check/Setup Gemini
    if not _configure_genai():
        return {"response": "", "actions": []}

    try:
        model = genai.GenerativeModel('gemini-pro')
        
        # Build prompt - Strict JSON enforcement
        system_instruction = (
            "You are a helpful PC assistant. Output ONLY valid JSON."
            "Schema: {\"response\": \"short text reply\", \"actions\": [{\"type\": \"...\", \"parameters\": {...}}]}"
            "Action types: [\"whatsapp_send\", \"open\", \"search\", \"play_song\", \"volume\", \"brightness\", \"timer\", \"reminder\"]."
            "For general queries, set actions=[]. Keep response concise."
        )

        history_context = ""
        if memory:
             try:
                 recent = memory.get_history()[-4:] # Last 4 messages
                 for role, msg in recent:
                     history_context += f"{role}: {msg}\n"
             except Exception:
                 pass
        
        full_prompt = f"{system_instruction}\nContext:\n{history_context}\nUser: {user_text}\nJSON:"
        
        response = model.generate_content(full_prompt)
        if not response or not response.text:
             return {"response": "", "actions": []}
             
        raw_text = response.text.strip()
        
        # Strip markdown code blocks if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
            
        try:
            data = json.loads(raw_text)
            if isinstance(data, dict):
                return {
                    "response": data.get("response", ""),
                    "actions": data.get("actions", [])
                }
        except json.JSONDecodeError:
            pass
            
        return {"response": "", "actions": []}
            
    except Exception as e:
        return {"response": "", "actions": []}


def simple_llm_query(prompt: str) -> str:
    """Helper for direct text generation (e.g. for WhatsApp composing)."""
    if not _configure_genai():
        return ""
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip() if response and response.text else ""
    except Exception:
        return ""
