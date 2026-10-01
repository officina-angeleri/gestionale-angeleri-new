import requests
import hashlib
import base64
import urllib3

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

idx = r_menu.text.find("notifyBkode")
if idx != -1:
    print(r_menu.text[max(0, idx-500):idx+500])
