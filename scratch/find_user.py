import json
import re

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

found = set()
for e in har['log']['entries']:
    text = e['response']['content'].get('text', '')
    for m in re.finditer(r'(user|utente|login|username|operatore)\s*[:=]\s*["\']([^"\']+)["\']', text, re.I):
        found.add(f"{m.group(1)}: {m.group(2)}")

for item in sorted(found):
    print(item)
