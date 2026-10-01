import json
import re

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for entry in har['log']['entries']:
    if 'menujson' in entry['request']['url']:
        text = entry['response']['content'].get('text', '')
        # Print all {text:'...', ... object: '...'}
        matches = re.findall(r"text:'([^']*)',id:'([^']*)',icon:[^,]*,object:\s*'([^']*)'", text)
        for t, mid, obj in matches:
            clean_t = re.sub(r'<[^>]+>', '', t).strip()
            if any(k in clean_t.lower() for k in ['fattur', 'acquist', 'vendit', 'ddt', 'ordin', 'listin', 'articol']):
                print(f"{clean_t:45} | object: {obj:20} | id: {mid}")
