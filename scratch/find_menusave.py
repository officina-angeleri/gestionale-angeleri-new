import requests
import hashlib
import base64
import urllib3
import re

urllib3.disable_warnings()

s = requests.Session()
s.verify = False
headers = {'User-Agent': 'Mozilla/5.0'}

s.post('https://www.bkode.cloud/menu/index', data={
    'user': 'sim',
    'passwd': hashlib.sha1(b'ma002').hexdigest(),
    'language': 'IT',
    'thema': ''
}, headers=headers)

b64_user = base64.b64encode(b'sim').decode('utf-8')
r = s.get(f'https://www.bkode.cloud/menu/index/{b64_user}/', headers=headers)

# Find all occurrences of menu/save or company
idx = 0
while True:
    pos = r.text.find('menu/save', idx)
    if pos == -1:
        break
    print("--- SNIPPET around menu/save ---")
    print(r.text[max(0, pos-200):min(len(r.text), pos+400)])
    idx = pos + 9
