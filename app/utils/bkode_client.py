"""
Client HTTP specializzato per l'integrazione con l'ERP B-Kode (bkode.cloud).
Gestisce in modo trasparente:
- Autenticazione con hashing SHA-1
- Rinnovo automatico della sessione CodeIgniter (ci_session)
- Estrazione Listini Fornitori (Acquisti) e Listini Clienti (Vendite)
- Estrazione Fatture Clienti (Vendite) e Fatture Fornitori (Acquisti)
- Estrazione Nuovi Articoli a magazzino
"""

import requests
import hashlib
import base64
import json
import re
import urllib3
import logging
from typing import Optional, List, Dict, Any

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

class BKodeClient:
    BASE_URL = "https://www.bkode.cloud"
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, cookie: Optional[str] = None):
        self.session = requests.Session()
        self.session.verify = False
        
        from app.utils.settings import SettingsManager
        self.settings_mgr = SettingsManager()
        
        self.username = username or self.settings_mgr.settings.get('bkode_username', 'Angeleri SRL')
        self.password = password or self.settings_mgr.settings.get('bkode_password', '')
        self.cookie = cookie or self.settings_mgr.settings.get('bkode_cookie', '')
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/panel/grid/mgartList/angeleri/401015/"
        })
        
        if self.cookie:
            self._apply_cookie(self.cookie)

    def _apply_cookie(self, cookie_val: str):
        self.cookie = cookie_val
        self.session.cookies.set("ci_session", requests.utils.unquote(cookie_val), domain="www.bkode.cloud")
        self.session.headers["Cookie"] = f"ci_session={cookie_val}"

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Effettua il login su B-Kode calcolando l'hash SHA-1 della password."""
        user = username or self.username
        pwd = password or self.password
        
        if not user or not pwd:
            logger.warning("[B-Kode] Credenziali non specificate per il login automatico.")
            return False
            
        sha1_pwd = hashlib.sha1(pwd.encode('utf-8')).hexdigest() if len(pwd) != 41 else pwd
        login_url = f"{self.BASE_URL}/menu/index"
        
        payload = {
            "user": user,
            "passwd": sha1_pwd,
            "language": "IT",
            "thema": ""
        }
        
        try:
            r = self.session.post(login_url, data=payload, timeout=15)
            if "OK" in r.text:
                # Estrai il nuovo cookie ci_session
                new_cookie = self.session.cookies.get("ci_session")
                if new_cookie:
                    self._apply_cookie(new_cookie)
                    self.settings_mgr.settings['bkode_cookie'] = new_cookie
                    self.settings_mgr.save_settings()
                    
                # Inizializza il contesto menu utente
                b64_user = base64.b64encode(user.encode('utf-8')).decode('utf-8')
                self.session.get(f"{self.BASE_URL}/menu/index/{b64_user}/", timeout=10)
                logger.info(f"[B-Kode] Login effettuato con successo per l'utente '{user}'.")
                return True
            else:
                logger.error(f"[B-Kode] Login fallito. Risposta del server: {r.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"[B-Kode] Errore di rete durante il login: {e}")
            return False

    def ensure_authenticated(self) -> bool:
        """Verifica se la sessione corrente è attiva. Se scaduta, esegue il re-login."""
        test_url = f"{self.BASE_URL}/panel/gridjson/liscliList/angeleri/"
        try:
            r = self.session.post(test_url, data={"start": "0", "limit": "1"}, timeout=10)
            if r.status_code == 200 and not r.text.strip().startswith("<!DOCTYPE html"):
                return True
        except Exception:
            pass
            
        logger.info("[B-Kode] Sessione scaduta o non valida. Tento il rinnovo...")
        return self.login()

    def _clean_json(self, raw_text: str) -> str:
        """Rimuove costrutti JS non-standard (come new Date(...)) generati da ExtJS."""
        return re.sub(r'new\s+Date\([^)]*\)', '""', raw_text)

    def _post_grid(self, grid_name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Esegue una chiamata POST a un endpoint gridjson di B-Kode con gestione auto-login."""
        url = f"{self.BASE_URL}/panel/gridjson/{grid_name}/angeleri/"
        
        for attempt in range(2):
            try:
                r = self.session.post(url, data=payload, timeout=30)
                if r.status_code == 200 and not r.text.strip().startswith("<!DOCTYPE html"):
                    try:
                        clean_text = self._clean_json(r.text)
                        return json.loads(clean_text)
                    except json.JSONDecodeError as jde:
                        logger.warning(f"[B-Kode] Errore parsing JSON {grid_name}: {jde}")
                        return None
                elif r.status_code == 200 and "login" in r.text.lower():
                    # Sessione scaduta: effettua il login e riprova
                    if self.login():
                        continue
                    else:
                        break
            except Exception as e:
                logger.error(f"[B-Kode] Errore richiesta {grid_name}: {e}")
                break
        return None

    # ==========================================
    # METODI DI ESTRAZIONE LISTINI PREZZI
    # ==========================================
    
    def fetch_purchase_price_lists(self, limit: int = 250) -> List[Dict[str, Any]]:
        """Estrae l'elenco dei listini di acquisto fornitori (lisforList)."""
        data = self._post_grid("lisforList", {"start": "0", "limit": str(limit)})
        return data.get("items", []) if data else []

    def fetch_purchase_price_list_items(self, list_id: Optional[int] = None, limit: int = 10000) -> List[Dict[str, Any]]:
        """Estrae tutte le righe articolo associate ai listini di acquisto fornitori (lisforListR)."""
        payload = {"start": "0", "limit": str(limit)}
        if list_id:
            payload["master_key"] = str(list_id)
            payload["inner"] = "true"
            payload["store_filter"] = f" AND lir_lit_id = '{list_id}'"
        data = self._post_grid("lisforListR", payload)
        return data.get("items", []) if data else []

    def fetch_sales_price_lists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Estrae l'elenco dei listini di vendita clienti (liscliList)."""
        data = self._post_grid("liscliList", {"start": "0", "limit": str(limit)})
        return data.get("items", []) if data else []

    def fetch_sales_price_list_items(self, list_id: Optional[int] = None, limit: int = 10000) -> List[Dict[str, Any]]:
        """Estrae le righe articolo associate ai listini di vendita clienti (liscliListR)."""
        payload = {"start": "0", "limit": str(limit)}
        if list_id:
            payload["master_key"] = str(list_id)
            payload["inner"] = "true"
            payload["store_filter"] = f" AND lir_vlt_id = '{list_id}'"
        data = self._post_grid("liscliListR", payload)
        return data.get("items", []) if data else []

    # ==========================================
    # METODI DI ESTRAZIONE FATTURE
    # ==========================================

    def fetch_sales_invoices(self, start: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Estrae le testate delle fatture clienti di vendita (fatcliList)."""
        data = self._post_grid("fatcliList", {"start": str(start), "limit": str(limit)})
        return data.get("items", []) if data else []

    def fetch_sales_invoice_items(self, start: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
        """Estrae il dettaglio righe vendute nelle fatture clienti (fatcliListD)."""
        data = self._post_grid("fatcliListD", {"start": str(start), "limit": str(limit)})
        return data.get("items", []) if data else []

    def fetch_purchase_invoices(self, start: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Estrae le fatture elettroniche di acquisto fornitore (fatforxmlList)."""
        data = self._post_grid("fatforxmlList", {"start": str(start), "limit": str(limit)})
        return data.get("items", []) if data else []

    # ==========================================
    # METODI DI ESTRAZIONE ARTICOLI CATALOGO
    # ==========================================

    def fetch_products(self, start: int = 0, limit: int = 200, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Estrae articoli dal catalogo generale B-Kode (mgartList)."""
        payload = {"start": str(start), "limit": str(limit)}
        if filter_type:
            payload["filter"] = json.dumps([{"field": "art_tipo", "data": {"type": "string", "value": filter_type}}])
        data = self._post_grid("mgartList", payload)
        return data.get("items", []) if data else []
