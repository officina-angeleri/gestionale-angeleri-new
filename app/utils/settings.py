import json
import os

class SettingsManager:
    def __init__(self, settings_file='settings.json'):
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
