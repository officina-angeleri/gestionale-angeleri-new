import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for i, e in enumerate(har['log']['entries']):
    req = e['request']
    url = req['url']
    post = req.get('postData', {}).get('text', '')
    query = req.get('queryString', [])
    
    found = []
    if 'angeleri' in url:
        found.append('in url')
    if 'angeleri' in post:
        found.append('in post')
    for q in query:
        if 'angeleri' in str(q):
            found.append('in query')
    if found:
        print(f"Entry {i:2d}: [{req['method']}] {url} -> {found}")
        if post:
            print("   POST:", post[:120])
