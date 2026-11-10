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
from typing import Optional, List, Dict, Any, Union

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

    def download_purchase_invoice_xml(self, fxml_id: int, file_name: str) -> Optional[bytes]:
        """Scarica il file XML originale della fattura elettronica SDI da B-Kode Cloud."""
        b64_file = base64.b64encode(file_name.encode('utf-8')).decode('utf-8')
        url = f"{self.BASE_URL}/panel/attachment/angeleri/show/fatforxmlList/fxml_file/{fxml_id}/grid/{b64_file}"
        try:
            r = self.session.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 100:
                return r.content
            logger.warning(f"[B-Kode] Download XML acquisto fxml_id={fxml_id} fallito (Status: {r.status_code}, len={len(r.content)})")
        except Exception as e:
            logger.error(f"[B-Kode] Errore di rete download XML acquisto fxml_id={fxml_id}: {e}")
        return None

    def download_sales_invoice_xml(self, fxml_id: int, file_name: str) -> Optional[bytes]:
        """Scarica il file XML originale della fattura elettronica clienti da B-Kode Cloud (fatclixmlList)."""
        b64_file = base64.b64encode(file_name.encode('utf-8')).decode('utf-8')
        url = f"{self.BASE_URL}/panel/attachment/angeleri/show/fatclixmlList/fxml_file/{fxml_id}/grid/{b64_file}"
        try:
            r = self.session.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 100:
                return r.content
            logger.warning(f"[B-Kode] Download XML vendita fxml_id={fxml_id} fallito (Status: {r.status_code}, len={len(r.content)})")
        except Exception as e:
            logger.error(f"[B-Kode] Errore di rete download XML vendita fxml_id={fxml_id}: {e}")
        return None

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

    def fetch_product_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Cerca un singolo articolo su B-Kode per codice esatto (mgartList)."""
        if not code or not code.strip():
            return None
        payload = {
            "start": "0", "limit": "1",
            "filter": json.dumps([{"field": "art_code", "data": {"type": "string", "value": code.strip()}}])
        }
        data = self._post_grid("mgartList", payload)
        items = data.get("items", []) if data else []
        return items[0] if items else None

    # ==========================================
    # METODI DI GESTIONE ARTICOLI FORNITORI (MGAFO)
    # ==========================================

    def fetch_bkode_suppliers(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Cerca l'ID e la Ragione Sociale dei fornitori da B-Kode (storeCombo_afo_for)."""
        url = f"{self.BASE_URL}/panel/combojson/mgafoForm/afo_for/angeleri/"
        payload = {
            "object": "mgafoForm",
            "field": "afo_for",
            "filter": "for_st=1",
            "query": query.strip() if query else "",
            "start": "0",
            "limit": str(limit)
        }
        try:
            r = self.session.post(url, data=payload, timeout=15)
            if r.status_code == 200 and not r.text.strip().startswith("<!DOCTYPE"):
                clean = self._clean_json(r.text)
                data = json.loads(clean)
                return data.get("rows", [])
        except Exception as e:
            logger.error(f"[B-Kode] Errore lookup fornitori B-Kode: {e}")
        return []

    def fetch_bkode_supplier_articles(self, start: int = 0, limit: int = 500) -> Optional[Dict[str, Any]]:
        """
        Estrae la lista delle associazioni Codice Fornitore <-> Ns. Codice da B-Kode (mgafoList).
        Ritorna un dizionario {'totalCount': int, 'items': List[Dict]} oppure None.
        """
        url = f"{self.BASE_URL}/panel/gridjson/mgafoList/angeleri/dummy/"
        payload = {
            "start": str(start),
            "limit": str(limit),
            "store_filter": " AND 1",
            "lightWeight": "true",
            "ext": "js"
        }
        headers = {
            "Referer": f"{self.BASE_URL}/panel/mixed/mgafoForm/mgafoList/0/0/0/obj_0/angeleri/0/0/0/W11bW3xdXQ==//"
        }
        try:
            r = self.session.post(url, data=payload, headers=headers, timeout=30)
            if r.status_code == 200 and not r.text.strip().startswith("<!DOCTYPE"):
                clean = self._clean_json(r.text)
                return json.loads(clean)
            else:
                logger.warning(f"[B-Kode] Risposta non JSON da mgafoList (status={r.status_code})")
        except Exception as e:
            logger.error(f"[B-Kode] Errore richiesta mgafoList: {e}")
        return None

    def _to_php_array(self, d: Dict[str, Any]) -> str:
        """Converte un dizionario Python in una stringa serializzata PHP compatibile con ExtJS js_array_to_php_array."""
        s = ""
        for k, v in d.items():
            sk = str(k)
            sv = str(v)
            s += f's:{len(sk)}:"{sk}";s:{len(sv)}:"{sv}";'
        return f'a:{len(d)}:{{{s}}}'

    def save_bkode_supplier_article(
        self,
        bkode_supplier_id: Union[int, str],
        supplier_code: str,
        internal_code: str,
        afo_id: Union[int, str] = 0,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Salva o aggiorna un'associazione Articolo Fornitore direttamente nel form B-Kode (mgafoForm -> panel/dbform).
        - bkode_supplier_id: ID fornitore B-Kode (es. '474')
        - supplier_code: Codice articolo del fornitore (es. '03810620')
        - internal_code: Codice articolo interno Angeleri (es. 'A850-0050')
        - afo_id: 0 o -1 per nuovo inserimento, altrimenti ID riga per aggiornamento
        """
        import urllib.parse

        cmd = "update" if str(afo_id) not in ("0", "-1", "") else "insert"
        key_val = str(afo_id) if cmd == "update" else "0"

        vals = {
            "afo_for": str(bkode_supplier_id),
            "afo_code": supplier_code.strip(),
            "afo_ns_art": internal_code.strip(),
            "afo_id": key_val,
            "afo_soc": "01",
            "afo_note": notes.strip() if notes else ""
        }

        fields_str = "::".join(vals.keys()) + "::"
        values_str = "::".join(vals.values()) + "::"
        php_arr = self._to_php_array(vals)
        escaped_php_arr = urllib.parse.quote(php_arr)

        payload = {
            "code": "mgafoForm",
            "cmd": cmd,
            "key_value": key_val,
            "fields": fields_str,
            "values": values_str,
            "values2": escaped_php_arr,
            "company": "angeleri",
            "afo_for": str(bkode_supplier_id),
            "afo_code": supplier_code.strip(),
            "afo_ns_art": internal_code.strip(),
            "afo_id": key_val,
            "afo_soc": "01",
            "afo_note": notes.strip() if notes else ""
        }

        headers = {
            "Referer": f"{self.BASE_URL}/panel/mixed/mgafoForm/mgafoList/0/0/0/obj_0/angeleri/0/0/0/W11bW3xdXQ==//"
        }

        url = f"{self.BASE_URL}/panel/dbform"
        try:
            r = self.session.post(url, data=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                try:
                    res_json = json.loads(r.text)
                    if res_json.get("success"):
                        logger.info(f"[B-Kode] Salvataggio articolo fornitore riuscito: afo_id={res_json.get('id')}")
                        return {"success": True, "id": res_json.get("id"), "raw": res_json}
                    else:
                        logger.warning(f"[B-Kode] Salvataggio rifiutato: {r.text}")
                        return {"success": False, "message": res_json.get("message") or r.text}
                except Exception:
                    if "success" in r.text.lower():
                        return {"success": True, "raw": r.text}
                    return {"success": False, "message": r.text}
            return {"success": False, "message": f"HTTP {r.status_code}"}
        except Exception as e:
            logger.error(f"[B-Kode] Errore di rete salvataggio articolo fornitore: {e}")
            return {"success": False, "message": str(e)}
