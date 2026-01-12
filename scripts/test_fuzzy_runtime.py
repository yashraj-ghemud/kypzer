import importlib, sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
importlib.invalidate_caches()
m = importlib.import_module('src.assistant.actions')
print('has:', hasattr(m, '_fuzzy_name_match'))
try:
    print('fn:', m._fuzzy_name_match('wps','wps office'))
except Exception as e:
    print('call error:', e)
