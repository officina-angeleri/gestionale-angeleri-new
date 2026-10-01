import json
import os
import sys

class SettingsManager:
    def __init__(self, settings_file='settings.json'):
        if not os.path.isabs(settings_file):
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            candidate = os.path.join(base_dir, settings_file)
            if os.path.exists(candidate) or not os.path.exists(os.path.join(os.getcwd(), settings_file)):
                settings_file = candidate
            else:
                settings_file = os.path.join(os.getcwd(), settings_file)
        self.settings_file = settings_file
        self.settings = self.load_settings()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Errore nel salvataggio delle impostazioni: {e}")

    def get_db_path(self):
        return self.settings.get('db_path')

    def set_db_path(self, path):
        self.settings['db_path'] = path
        self.save_settings()

    def should_remember_db(self):
        return self.settings.get('remember_db', False)

    def set_remember_db(self, value):
        self.settings['remember_db'] = value
        self.save_settings()

    def get_gemini_api_key(self):
        # Prima controlla nelle impostazioni salvate, poi nella variabile d'ambiente
        return self.settings.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY', '')

    def set_gemini_api_key(self, key):
        self.settings['gemini_api_key'] = key.strip() if key else ''
        self.save_settings()

    def get_gemini_model(self):
        m = self.settings.get('gemini_model')
        if not m or "2.5-flash" in m and "lite" not in m:
            return 'gemini-flash-latest'
        return m

    def set_gemini_model(self, model):
        self.settings['gemini_model'] = model
        self.save_settings()

    def get_bkode_username(self):
        return self.settings.get('bkode_username', 'ma002')

    def set_bkode_username(self, username):
        self.settings['bkode_username'] = username.strip() if username else ''
        self.save_settings()

    def get_bkode_password(self):
        return self.settings.get('bkode_password', '')

    def set_bkode_password(self, password):
        self.settings['bkode_password'] = password
        self.save_settings()

    def get_bkode_cookie(self):
        return self.settings.get('bkode_cookie', '')

    def set_bkode_cookie(self, cookie):
        self.settings['bkode_cookie'] = cookie.strip() if cookie else ''
        self.save_settings()

    def get_bkode_sync_interval(self):
        return int(self.settings.get('bkode_sync_interval', 15))

    def set_bkode_sync_interval(self, minutes):
        self.settings['bkode_sync_interval'] = int(minutes)
        self.save_settings()
