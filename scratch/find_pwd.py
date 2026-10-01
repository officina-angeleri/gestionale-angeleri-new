import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for i, e in enumerate(har['log']['entries']):
    req_text = str(e['request'])
    resp_text = str(e['response'])
    for kw in ['passwd', 'password', 'pwd']:
        if kw in req_text.lower() or kw in resp_text.lower():
            print(f"Keyword '{kw}' found in entry {i}")
