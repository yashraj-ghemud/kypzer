from src.assistant.multi_task_parser import is_multi_task_command, parse_multi_task_command

tests = [
    ('open chrome and search best laptops under 50k and click on first link', False),
    ('open calc and 2+2', False),
    ('open youtube in chrome', False),
    ('search python on stackoverflow', False),
    ('open games website', False),
    ('send good night message Tu papa and then play Spotify song', True),
    ('send hi to mom and play music', True),
    ('turn off wifi and mute volume', False),  # Both are system settings - handled by regular NLU
    ('open bluetooth settings', False),
    ('send message to mom then turn off wifi', True),  # messaging + system
    ('play song and send hi to dad', True),  # music + messaging
    ('mute volume then play spotify', True),  # has "then" + 2 action verbs
]

print('Testing is_multi_task_command:')
passed = 0
failed = 0
for cmd, expected in tests:
    result = is_multi_task_command(cmd)
    status = 'OK' if result == expected else 'FAIL'
    if result == expected:
        passed += 1
    else:
        failed += 1
    short_cmd = cmd if len(cmd) < 55 else cmd[:52] + '...'
    print(f'{status}: "{short_cmd}" => {result} (expected {expected})')

print(f'\nTotal: {passed}/{passed+failed} passed')
