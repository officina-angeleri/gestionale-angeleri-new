import requests
import urllib3

urllib3.disable_warnings()

s = requests.Session()
s.verify = False
r = s.get('https://www.bkode.cloud/')
print("Page length:", len(r.text))
with open('scratch/login_page.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print("Saved to scratch/login_page.html")
