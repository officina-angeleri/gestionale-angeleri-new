import requests
import hashlib
import base64
import urllib3
import json

urllib3.disable_warnings()

s = requests.Session()
s.verify = False
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest'
}

s.post('https://www.bkode.cloud/menu/index', data={
    'user': 'sim',
    'passwd': hashlib.sha1(b'ma002').hexdigest(),
    'language': 'IT',
    'thema': ''
}, headers=headers)

b64_user = base64.b64encode(b'sim').decode('utf-8')
s.get(f'https://www.bkode.cloud/menu/index/{b64_user}/', headers=headers)

# Fetch jsonmenu
r_menu = s.post('https://www.bkode.cloud/menu/jsonmenu/ma002', headers=headers)
print('jsonmenu status:', r_menu.status_code, 'len:', len(r_menu.text))
try:
    data = r_menu.json()
    print('Type of data:', type(data))
    if isinstance(data, list):
        print('Items in menu:', len(data))
        for item in data[:5]:
            print(' ', item.get('text'), '| company:', item.get('company_code'), '| object:', item.get('object'), '| code:', item.get('code'))
except Exception as e:
    print('Error json:', e, r_menu.text[:200])
