import os
import json
import base64
import sqlite3
import ctypes
from ctypes import wintypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_char))]

def dpapi_decrypt(encrypted_bytes):
    blob_in = DATA_BLOB(len(encrypted_bytes), ctypes.create_string_buffer(encrypted_bytes))
    blob_out = DATA_BLOB()
    if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        cbData = int(blob_out.cbData)
        pbData = blob_out.pbData
        buffer = ctypes.string_at(pbData, cbData)
        ctypes.windll.kernel32.LocalFree(pbData)
        return buffer
    return None

def copy_locked_file(src, dst):
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    
    handle = ctypes.windll.kernel32.CreateFileW(
        src, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        raise Exception(f"Cannot open locked file: {src}")
    
    with open(dst, 'wb') as f_out:
        buf = ctypes.create_string_buffer(64 * 1024)
        bytes_read = wintypes.DWORD()
        while True:
            success = ctypes.windll.kernel32.ReadFile(handle, buf, len(buf), ctypes.byref(bytes_read), None)
            if not success or bytes_read.value == 0:
                break
            f_out.write(buf.raw[:bytes_read.value])
    ctypes.windll.kernel32.CloseHandle(handle)

local_state_path = os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data\\Local State')
cookies_path = os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Network\\Cookies')

if not os.path.exists(cookies_path):
    cookies_path = os.path.expanduser('~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cookies')

print('Local state exists:', os.path.exists(local_state_path))
print('Cookies path exists:', os.path.exists(cookies_path))

if os.path.exists(local_state_path) and os.path.exists(cookies_path):
    with open(local_state_path, 'r', encoding='utf-8') as f:
        local_state = json.load(f)
    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])[5:]
    key = dpapi_decrypt(encrypted_key)

    os.makedirs('scratch', exist_ok=True)
    copy_locked_file(cookies_path, 'scratch/chrome_cookies.db')
    conn = sqlite3.connect('scratch/chrome_cookies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%bkode.cloud%'")
    rows = cursor.fetchall()
    print('Found bkode cookies in Chrome:', len(rows))
    aesgcm = AESGCM(key)
    for name, enc_val in rows:
        try:
            nonce = enc_val[3:15]
            payload = enc_val[15:]
            val = aesgcm.decrypt(nonce, payload, None).decode('utf-8')
            print(f"  {name} = {val[:60]}...")
            if name == 'ci_session':
                from app.utils.settings import SettingsManager
                sm = SettingsManager()
                sm.set_bkode_cookie(val)
                print("  --> SALVATO COOKIE CI_SESSION ATTUALE IN SETTINGS.JSON!")
        except Exception as e:
            print(f"  Errore decrittazione cookie {name}: {e}")
