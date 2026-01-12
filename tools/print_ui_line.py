p = r'c:\Users\yashraj\Desktop\drawings\pc sontroller\src\assistant\ui.py'
lines = open(p, 'r', encoding='utf-8').read().splitlines()
ln = 1378
print(f'Total lines: {len(lines)}')
if len(lines) >= ln:
    print(f'Line {ln}: ' + lines[ln-1])
else:
    print('File shorter than requested line')
