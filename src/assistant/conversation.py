from collections import deque
from typing import Deque, Dict, Any, List


class ConversationMemory:
    """Simple rolling memory for recent turns.

    Stores tuples of (role, text), where role is 'user' or 'assistant'.
    """

    def __init__(self, capacity: int = 40):
        self.capacity = capacity
        self._items: Deque[Dict[str, Any]] = deque(maxlen=capacity)

    def add_user(self, text: str):
        self._items.append({"role": "user", "text": text})

    def add_assistant(self, text: str):
        self._items.append({"role": "assistant", "text": text})

    def as_list(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def clear(self):
        self._items.clear()

    def last_user(self) -> str:
        for item in reversed(self._items):
            if item["role"] == "user":
                return item["text"]
        return ""
