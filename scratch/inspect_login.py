import requests
import re
import urllib3
urllib3.disable_warnings()

s = requests.Session()
s.verify = False
r = s.get('https://www.bkode.cloud/')
print('Base URL status:', r.status_code, 'Final URL:', r.url)

forms = re.findall(r'<form[^>]*action=["\']([^"\']*)["\'][^>]*>', r.text, re.IGNORECASE)
print('Form actions:', forms)
inputs = re.findall(r'<input[^>]*name=["\']([^"\']*)["\'][^>]*>', r.text, re.IGNORECASE)
print('Input names:', inputs)
print('\nPage text snippet:')
for line in r.text.splitlines():
    if any(k in line.lower() for k in ['login', 'user', 'pass', 'form', 'action', 'token']):
        print(' ', line.strip()[:100])
