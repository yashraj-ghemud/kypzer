import importlib, sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
importlib.invalidate_caches()
from src.assistant import actions

print('calling uninstall dry-run...')
try:
    res = actions._uninstall({'name': 'WPS Office', 'dry_run': True, 'require_confirm': False})
    print('result:', res)
except Exception as e:
    import traceback
    traceback.print_exc()
    print('exception:', e)
