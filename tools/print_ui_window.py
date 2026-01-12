p = r'c:\Users\yashraj\Desktop\drawings\pc sontroller\src\assistant\ui.py'
lines = open(p, 'r', encoding='utf-8').read().splitlines()
start=1368
end=1390
print(f'Total lines: {len(lines)}')
for i in range(start-1, min(end, len(lines))):
    print(f'{i+1:5}: {lines[i]}')
