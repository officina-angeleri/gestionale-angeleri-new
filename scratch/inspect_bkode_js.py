import requests
import hashlib
import base64
import urllib3
import re

urllib3.disable_warnings()

s = requests.Session()
s.verify = False
headers = {'User-Agent': 'Mozilla/5.0'}

# Download main javascript files and check for switch or company
for js in ['javaphp_2.4.js', 'normalizeFormValues_2.1.js']:
    r = s.get(f'https://www.bkode.cloud/assets/js/{js}', headers=headers)
    for line in r.text.splitlines():
        if any(k in line.lower() for k in ['company', 'azienda', 'switch', 'database', 'connect', 'login']):
            print(f"[{js}]", line.strip()[:120])
