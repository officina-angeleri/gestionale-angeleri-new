import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for i, e in enumerate(har['log']['entries']):
    url = e['request']['url']
    for term in ['change', 'select', 'switch', 'set', 'company', 'azienda', 'soc', 'session']:
        if term in url.lower():
            print(f"Entry {i}: {url}")
            break
