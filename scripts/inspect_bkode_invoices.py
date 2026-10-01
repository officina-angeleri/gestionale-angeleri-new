import os
import requests
import urllib3
import re
import json

urllib3.disable_warnings()

import sys
sys.path.insert(0, '.')
from app.utils.settings import SettingsManager

sm = SettingsManager()
cookie = sm.get_bkode_cookie()

s = requests.Session()
s.verify = False
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': 'https://www.bkode.cloud',
    'Cookie': f'ci_session={cookie}'
})

# 1. Purchase invoices
r = s.post('https://www.bkode.cloud/panel/gridjson/fatforxmlList/angeleri/', data={'start': '0', 'limit': '2'})
print("fatforxmlList status:", r.status_code)
print("fatforxmlList text preview:", repr(r.text[:300]))
clean_text = re.sub(r'new\s+Date\([^)]*\)', '""', r.text)
if not r.text.strip().startswith("<!DOCTYPE") and r.text.strip():
    data_p = json.loads(clean_text)
else:
    data_p = {}
print("Purchase invoice total:", data_p.get("totalCount"))
if data_p.get('items'):
    print("Purchase invoice sample keys:", list(data_p['items'][0].keys()))
    print("Purchase invoice sample:", json.dumps(data_p['items'][0], indent=2))

# 2. Sales invoices
r2 = s.post('https://www.bkode.cloud/panel/gridjson/fatcliList/angeleri/', data={'start': '0', 'limit': '2'})
clean_text2 = re.sub(r'new\s+Date\([^)]*\)', '""', r2.text)
data_s = json.loads(clean_text2)
print("\nSales invoice total:", data_s.get("totalCount"))
if data_s.get('items'):
    print("Sales invoice sample keys:", list(data_s['items'][0].keys()))
    print("Sales invoice sample:", json.dumps(data_s['items'][0], indent=2))
