import socket
import time
import re

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(65)
try:
    sock.connect(('127.0.0.1', 10111))
    print('TCP connected, collecting 60s data...')
except Exception as e:
    print(f'Connect failed: {e}')
    exit(1)

lines = []
start = time.time()
while time.time() - start < 62:
    try:
        data = sock.recv(4096).decode('ascii', errors='replace')
        for line in data.split('\n'):
            line = line.strip()
            if line.startswith('$'):
                lines.append(line)
    except socket.timeout:
        break
    except Exception:
        break

sock.close()
print(f'Done: {len(lines)} sentences')

groups = {}
for line in lines:
    m = re.match(r'\$(?:[A-Z]{2})([A-Z]{3}),', line)
    if m:
        t = m.group(1)
        if t not in groups:
            groups[t] = []
        groups[t].append(line)

print(f'{len(groups)} sentence types')
for t in sorted(groups.keys()):
    print(f'  {t}: {len(groups[t])} sentences')

with open('nmea_output.txt', 'w', encoding='utf-8') as f:
    for line in lines:
        f.write(line + '\n')
print('Data saved to nmea_output.txt')
