import importlib,sys,os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
importlib.invalidate_caches()
from src.assistant import actions as a

examples = [
    'play me despacito',
    'por favor reproduce la cancion despacito',
    'pls play "Bohemian Rhapsody" by Queen',
    'कृपया गाना "tum hi ho" चलाओ',
    '播放 青花瓷',
    'can you play the song nothing else matters by metallica please',
    'i want to hear señorita by shawn mendes',
]

for t in examples:
    print('IN:', t)
    print('OUT:', a._parse_play_song_query(t))
    print('---')
