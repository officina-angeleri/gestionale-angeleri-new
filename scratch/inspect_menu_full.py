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

for line in r.text.splitlines():
    if any(k in line for k in ['TreeLoader', 'dataUrl', 'company', 'url:', 'location']):
        print(line.strip()[:140])
