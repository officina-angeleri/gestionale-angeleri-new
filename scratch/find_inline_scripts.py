import requests
import hashlib
import base64
import urllib3
import re

urllib3.disable_warnings()

s = requests.Session()
s.verify = False

s.post('https://www.bkode.cloud/menu/index', data={
    'user': 'sim',
    'passwd': hashlib.sha1(b'ma002').hexdigest(),
    'language': 'IT',
    'thema': ''
})

b64_user = base64.b64encode(b'sim').decode('utf-8')
r_menu = s.get(f'https://www.bkode.cloud/menu/index/{b64_user}/')

inline = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', r_menu.text, re.DOTALL)
for i, sc in enumerate(inline):
    print(f"=== Inline Script {i} (len: {len(sc)}) ===")
    print(sc.strip()[:600])
