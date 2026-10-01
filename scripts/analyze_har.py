import json
import re

har_path = r'c:\Users\Simone\.gemini\antigravity\scratch\.antigravity\Gestionale Angeleri\www.bkode.cloud.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har_data = json.load(f)

entry0 = har_data['log']['entries'][0]
entry0_html = entry0['response']['content'].get('text', '')

# Extract all data['...'] = '...';
matches = re.findall(r"data\['([^']+)'\]\s*=\s*'([^']*)';", entry0_html)
print(f"Total data fields found in Entry 0: {len(matches)}")
for k, v in matches:
    if v:
        print(f"  {k} = {v}")

print("\n--- Headers of Entry 0 ---")
for h in entry0['request']['headers']:
    print(f"  {h['name']}: {h['value'][:120]}")

print("\n--- Cookies of Entry 0 ---")
for c in entry0['request'].get('cookies', []):
    print(f"  {c['name']} = {c['value'][:60]}")

for i, entry in enumerate(har_data['log']['entries']):
    req = entry['request']
    url = req['url']
    if 'mgart' in url:
        print(f"Entry {i}: [{req.get('method')}] {url}")
        cookies = req.get('cookies', [])
        if cookies:
            print("   Cookies:", [(c['name'], c['value']) for c in cookies])
        post = req.get('postData', {}).get('text', '')
        if post:
            print("   POST payload:", post[:150])

