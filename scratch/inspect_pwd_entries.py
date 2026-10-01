import json

with open('www.bkode.cloud.har', 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

for idx in [9, 25, 32, 77, 100]:
    e = har['log']['entries'][idx]
    print(f"--- Entry {idx}: {e['request']['url']} ---")
    req_s = json.dumps(e['request'])
    resp_s = json.dumps(e['response'])
    for kw in ['password', 'pwd']:
        if kw in req_s.lower():
            print(f"  In Request ({kw}):", req_s[:200])
        if kw in resp_s.lower():
            # print snippet around kw
            pos = resp_s.lower().find(kw)
            print(f"  In Response ({kw}):", resp_s[max(0, pos-40):min(len(resp_s), pos+80)])
