import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for i, e in enumerate(har['log']['entries'][:25]):
    req = e['request']
    print(f"{i:2d}: [{req['method']}] {req['url']}")
