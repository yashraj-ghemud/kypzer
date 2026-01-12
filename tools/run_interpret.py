import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from src.assistant.nlu import interpret
import json

text = "paste and send to abhishek sir , nikita , rahul sir , balraju , ashish ghemud , saish , mummy , amit bhai , aryan , niketan , anuj , himesh , mummy , pimple , akash"
res = interpret(text)
print(json.dumps(res, ensure_ascii=False, indent=2))
