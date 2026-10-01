import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for i, e in enumerate(har['log']['entries']):
    text = e['response']['content'].get('text', '')
    if 'ma002' in text:
        print(f"Found in entry {i} url: {e['request']['url']}")
        lines = [line.strip() for line in text.splitlines() if 'ma002' in line]
        for l in lines[:5]:
            print("  ", l[:120])
