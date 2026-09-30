import os
import json
from google import genai
from google.genai import types
from app.utils.settings import SettingsManager
from app.database import get_db_session

OFFICINA_SYSTEM_INSTRUCTION = """Sei l'Assistente Intelligente di 'Officina Meccanica Angeleri'.
Il tuo compito è supportare il titolare e l'officina nella ricerca di ricambi, prezzi d'acquisto, prezzi di vendita, comparazione codici vecchi/nuovi e analisi clienti/fornitori.

REGOLE CRITICHE SULLE CODIFICHE DELL'OFFICINA:
1. Codici con prefisso 'A' (es. A850-0050, A650-0001, A550-...): sono articoli e componenti di acquisto commerciale (motori, cinghie, pignoni commerciali, cuscinetti, pneumatica).
2. Codici con prefisso 'L' (es. L010-..., L011-..., L040-..., L050-...): sono particolari a disegno di produzione/lavorazione interna:
   - L010: particolari in alluminio (es. rulli superiori, camicie, piastre)
   - L011: particolari in ferro (es. alberi, bussole)
   - L040: carpenteria e saldatura
   - L050: semilavorati e ingranaggi speciali (es. ingranaggi in fibra, pignoni speciali)
3. Codici numerici storici (es. 3150-12, 3100-20, 00ICT60-01): sono i vecchi codici ricambio o posizioni degli esplosi storici delle macchine (incollatrici MAV, ICT, ecc.), collegati N:1 ai nuovi codici master A o L.

ISTRUZIONI PER LE RICERCHE E RISPOSTE:
- Se l'utente chiede 'tutti i ... che trovi', 'elenco dei rulli', 'tutti i pignoni', 'cerca tutti gli articoli...', o cerca per tipologia/categoria di pezzo, USA SEMPRE lo strumento 'cerca_tutti_articoli'.
- Se l'utente menziona PIÙ CATEGORIE o RICAMBI nella stessa richiesta (es. 'cerca i rulli superiori, l'ingranaggio in fibra e il pignone'), invoca 'cerca_tutti_articoli' per CIASCUNA categoria separatamente (es. una chiamata per 'rullo superiore', una per 'ingranaggio fibra', una per 'pignone').
- Se l'utente chiede invece la scheda o il prezzo di uno o più ricambi SPECIFICI ben identificati da codice (es. 'L010-0009', '3150-12'), usa 'cerca_ricambio_360' o 'confronta_elenco_ricambi'.
- Rispondi sempre in italiano, in modo chiaro, professionale e ben formattato in tabelle Markdown.
- Nelle tabelle per elenchi articoli includi sempre: Codice Master, Descrizione, Categoria, Costo Standard (€), Prezzo Listino (€), ed eventuali Codici Esploso Legacy.
- Se l'utente usa parole trascritte dal parlato che contengono piccoli refusi (es. 'dazn 36' che significa 'da Z 36 denti' o 'disegno 3617/3618'), interpreta intelligentemente e cerca i codici pertinenti.

REGOLE PER LINK E APERTURA FATTURE:
- Quando citi o elenchi fatture nelle tabelle o nel testo (vendite clienti o acquisti fornitori), rendi SEMPRE il numero di fattura un link cliccabile:
  * Per fatture clienti/vendite: usa il link fornito nel tool o formato [Fattura NUMERO](app:invoice:sale:NUMERO:ANNO) (es. [Fattura 217](app:invoice:sale:217:2024), [Fattura 355](app:invoice:sale:355:2019)).
  * Per fatture fornitori/acquisti: usa formato [Fattura NUMERO](app:invoice:purchase:NUMERO).
- Se l'utente chiede esplicitamente di 'aprire', 'vedere tutta', o 'mostrare i dettagli' di una fattura (es. 'apri la fattura 217', 'mostrami tutta la fattura 217 di IEN INDUSTRIE'), USA LO STRUMENTO 'dettaglio_completo_fattura'.
- Nella risposta mostra il riepilogo della testata (cliente, data, totale), la tabella con tutte le righe e il link evidente:
  [Apri scheda a schermo intero della Fattura NUMERO](app:invoice:sale:NUMERO:ANNO)

REGOLE PER RICERCHE FATTURE (ES. 'cerca ultime 3 fatture euromarche', 'fatture di IEN', 'fatture 2024'):
- Quando l'utente chiede 'ultime fatture', 'fatture di [cliente o fornitore]' (es. 'cerca ultime 3 fatture euromarche'), 'fatture del cliente X', 'fatture emesse', 'fatture del 2024', USA SEMPRE lo strumento 'elenco_fatture'.
- ATTENZIONE: clienti abituali storici come EUROMARCHE SRL, IEN INDUSTRIE SPA, EUROSCARPA SRL, ecc. sono CLIENTI registrati nelle vendite! 'elenco_fatture' cerca automaticamente sia tra i clienti che tra i fornitori.
- REGOLA FONDAMENTALE SULLA NON RIPETIZIONE: Quando elenchi fatture di un cliente o fornitore (senza che sia stato chiesto uno specifico pezzo di ricambio), NON DEVI MAI ripetere la stessa fattura più volte per ogni articolo contenuto!
  Mostra ESATTAMENTE UNA SOLA RIGA PER CIASCUNA FATTURA in una tabella Markdown con colonne:
  | N. Fattura | Data | Cliente / Fornitore | Totale Documento (€) | N. Righe | Primo Articolo / Descrizione | Azione |
- Solo se l'utente chiede esplicitamente di cercare le fatture dove è presente un ARTICOLO SPECIFICO (es. 'in quali fatture abbiamo venduto il rullo morbido?'), allora e solo allora mostrerai le righe con il dettaglio del ricambio richiesto.

REGOLE PER ESPLOSI E DISTINTE MACCHINE (DISEGNI TECNICI PDF):
- Abbiamo archiviato nel database oltre 170 tavole/esplosi tecnici PDF delle macchine Angeleri (MAV 3150, ICT 60, ECOL 60, MAV 3024, TERMO 450, ecc.) con oltre 1.100 componenti e corrispondenze codici vecchi/nuovi.
- Se l'utente chiede 'in quale esploso trovo...', 'mostrami i componenti della 3150', 'che pezzo c'è alla posizione 80', 'trova il disegno del basamento', o chiede informazioni sulle tavole di montaggio delle macchine:
  USA SEMPRE lo strumento 'cerca_esploso_macchina'.
- Includi sempre nella tabella i campi: Macchina, Codice Tavola, Posizione nel Disegno (NUMERAZIONE_OLD), Codice Master, Descrizione, e il link cliccabile per aprire il PDF originale a tutto schermo:
  [📄 Apri PDF Esploso](app:diagram:ID_O_PATH)

REGOLE PER RICERCHE FORNITORI E STORICO PREZZI (ES. 'cerca ingranaggio z26 da imbg', 'prezzi sacchi'):
- FORNITORI COMMERCIALI: nel database dell'officina sono censiti 114 fornitori con decine di migliaia di acquisti.
  * I fornitori sono spesso abbreviati dall'utente:
    - 'IMBG' o 'i.m.b.g.' -> fornitore 'I.M.B.G. S.r.l.' (storico fornitore di trasmissione, cuscinetti, pignoni, pulegge e minuterie)
    - 'Sacchi' -> 'SACCHI GIUSEPPE S.P.A.' (materiale elettrico e sensori)
    - 'Carpanelli' -> 'CARPANELLI MOTORI ELETTRICI S.p.A.' (motori)
    - 'Alusic' -> 'ALUSIC S.r.l.' (profili alluminio e accessori)
    - 'Comel' -> 'COMEL SRL'
  * Se l'utente chiede prezzi o acquisti da un fornitore (es. 'cerca ingranaggio z26 dal fornitore i.m.b.g.'), invoca 'storico_prezzi_fornitore' passando il nome del fornitore (es. 'IMBG') e l'articolo (es. 'ingranaggio z26' o 'z26').
  * TERMINOLOGIA MECCANICA COMMERCIALE:
    - Nei cataloghi commerciali e nelle fatture fornitori (es. IMBG), i componenti a dentatura commerciale sono spesso descritti come 'PIGNONE' (es. 'PIGNONE SEMPLICE P.8x3 Z=26'), 'PULEGGIA' (es. 'PULEGGIA 27 T5 Z=26') o 'BARRA METRICA T5 Z=26'.
    - Il numero di denti è spesso indicato come 'Z=26' o 'Z 26' o 'Z26'.
    - Mostra all'utente sia gli acquisti trovati dal fornitore (es. il pignone commerciale Z=26 con numero di fattura e prezzo), sia l'eventuale corrispettivo a disegno interno officina (es. L050-0010) se pertinente.

REGOLE PER DISTINTE MATERIALI (BOM), LAVORAZIONI E CALCOLO COSTI:
- Per gli articoli a disegno di produzione (es. L010-0016, L011-..., L050-...):
  * Se l'utente chiede 'da cosa è composto', 'quali materiali servono', 'quante ore di macchina/lavoro ci vogliono', o 'calcola il costo di produzione':
    USA SEMPRE lo strumento 'calcola_costo_produzione'.
  * Mostra:
    1. Distinta Materiali (componenti, quantità, costo unitario)
    2. Ciclo Lavorazioni (fasi macchina es. Fresatura HURCO, Alesaggio, Attrezzaggio, con ore e tariffe)
    3. Riepilogo Costi: Totale Materiali + Totale Lavorazioni = Costo Produzione Stimato.
- Per i materiali commerciali (barre, tondi ottone/ferro/alluminio es. A102-0008):
  * Se l'utente chiede 'quanto costa uno spezzone di 200 mm di ottone...', 'calcola il costo per 150 mm di A102-0008', 'quanto pesa 300 mm...':
    USA SEMPRE lo strumento 'calcola_spezzone_materiale'.
  * Spiega chiaramente il calcolo: Lunghezza (mm ➔ m) × Fattore Conversione (kg/m) = Peso (kg) × Prezzo (€/kg) = Costo Totale.
"""

class GeminiAssistant:
    def __init__(self, controller):
        self.controller = controller
        self.settings = SettingsManager()
        self.api_key = self.settings.get_gemini_api_key()
        self.model_name = self.settings.get_gemini_model() or "gemini-flash-latest"
        # Se il modello salvato era quello deprecato, aggiornalo a gemini-flash-latest
        if "2.5-flash" in self.model_name and "lite" not in self.model_name:
            self.model_name = "gemini-flash-latest"
            self.settings.set_gemini_model(self.model_name)
            
        self.client = None
        self.chat = None
        
        if self.api_key:
            self._init_chat()

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    def update_config(self, api_key: str = None, model_name: str = None):
        if api_key:
            self.api_key = api_key.strip()
            self.settings.set_gemini_api_key(self.api_key)
        if model_name:
            self.model_name = model_name
            self.settings.set_gemini_model(self.model_name)
        self._init_chat()

    def reset_chat(self):
        self._init_chat()

    def _init_chat(self):
        if not self.is_configured():
            self.client = None
            self.chat = None
            return

        try:
            # Bypassa l'intercettazione SSL di antivirus come Avast su Windows
            http_opts = types.HttpOptions(client_args={'verify': False})
            self.client = genai.Client(api_key=self.api_key, http_options=http_opts)

            tools = [
                self.cerca_esploso_macchina,
                self.elenco_fatture,
                self.cerca_tutti_articoli,
                self.cerca_ricambio_360,
                self.confronta_elenco_ricambi,
                self.dettaglio_completo_fattura,
                self.storico_prezzi_fornitore,
                self.storico_vendite_cliente,
                self.dettaglio_fornitore,
                self.dettaglio_cliente,
                self.statistiche_generali_officina,
                self.calcola_costo_produzione,
                self.calcola_spezzone_materiale
            ]

            config = types.GenerateContentConfig(
                system_instruction=OFFICINA_SYSTEM_INSTRUCTION,
                tools=tools
            )
            self.chat = self.client.chats.create(model=self.model_name, config=config)
        except Exception as e:
            print(f"Errore inizializzazione Gemini Client: {e}")
            self.chat = None

    def send_message(self, prompt: str) -> str:
        if not self.is_configured():
            return (
                "⚠️ **API Key non configurata.**\n\n"
                "Per attivare l'assistente AI di Officina Angeleri, clicca sul pulsante **'⚙️ Imposta API Key'** "
                "in alto a destra e inserisci la tua chiave Google Gemini gratuita da Google AI Studio."
            )

        if not self.chat:
            self._init_chat()
            if not self.chat:
                return "❌ Errore durante l'inizializzazione della sessione con Google Gemini. Verifica la chiave API."

        try:
            response = self.chat.send_message(prompt)
            if response and response.text:
                return response.text
            return "Nessuna risposta ricevuta dal modello."
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return "⚠️ Quota API esaurita per questo minuto. Riprova tra 20-30 secondi."
            if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                # Il modello è temporaneamente sovraccarico su Google: fallback automatico immediato
                alt_model = "gemini-3.5-flash-lite" if self.model_name != "gemini-3.5-flash-lite" else "gemini-flash-latest"
                try:
                    self.model_name = alt_model
                    self.settings.set_gemini_model(self.model_name)
                    self._init_chat()
                    res = self.chat.send_message(prompt)
                    if res and res.text:
                        return res.text
                except Exception as ex:
                    return f"⚠️ I server di Google Gemini sono temporaneamente occupati (503). Riprova tra pochi secondi ({ex})."
            if "404" in err_str and "model" in err_str.lower():
                try:
                    self.model_name = "gemini-3.5-flash-lite"
                    self.settings.set_gemini_model(self.model_name)
                    self._init_chat()
                    res = self.chat.send_message(prompt)
                    return res.text
                except Exception as ex:
                    return f"❌ Errore modello: {ex}"
            if "API_KEY_INVALID" in err_str or ("400" in err_str and "key" in err_str.lower()):
                return "❌ La chiave Google Gemini API inserita non è valida. Clicca su '⚙️ Imposta API Key' per correggerla."
            return f"❌ Errore durante la comunicazione con Gemini: {err_str}"

    # =========================================================================
    # METODI DI SUPPORTO RICERCA INTELLIGENTE (FORNITORI, CLIENTI, SINONIMI)
    # =========================================================================

    @staticmethod
    def _find_matching_suppliers(session, search_str: str):
        from app.database import Supplier
        import re
        if not search_str:
            return []
        clean_raw = search_str.strip()
        clean_alpha = re.sub(r'[^a-zA-Z0-9]', '', clean_raw).lower()
        if not clean_alpha:
            return []
            
        # 1. Corrispondenza diretta ILIKE
        direct = session.query(Supplier).filter(Supplier.name.ilike(f"%{clean_raw}%")).all()
        if direct:
            return direct
            
        # 2. Corrispondenza alfanumerica normalizzata (es. imbg -> I.M.B.G. S.r.l., sacchi -> SACCHI GIUSEPPE S.P.A.)
        all_s = session.query(Supplier).all()
        matched = []
        for s in all_s:
            s_alpha = re.sub(r'[^a-zA-Z0-9]', '', (s.name or '').lower())
            if clean_alpha in s_alpha or (len(s_alpha) >= 3 and s_alpha in clean_alpha):
                matched.append(s)
        return matched

    @staticmethod
    def _find_matching_customers(session, search_str: str):
        from app.database import Customer
        import re
        if not search_str:
            return []
        clean_raw = search_str.strip()
        clean_alpha = re.sub(r'[^a-zA-Z0-9]', '', clean_raw).lower()
        if not clean_alpha:
            return []
            
        # 1. Corrispondenza diretta ILIKE
        direct = session.query(Customer).filter(Customer.name.ilike(f"%{clean_raw}%")).all()
        if direct:
            return direct
            
        # 2. Corrispondenza alfanumerica normalizzata
        all_c = session.query(Customer).all()
        matched = []
        for c in all_c:
            c_alpha = re.sub(r'[^a-zA-Z0-9]', '', (c.name or '').lower())
            if len(clean_alpha) >= 3 and (clean_alpha in c_alpha or c_alpha in clean_alpha):
                matched.append(c)
        return matched

    @staticmethod
    def _build_item_search_conditions(model_item, search_text: str):
        import re
        from sqlalchemy import or_, and_
        if not search_text:
            return None
            
        clean_text = search_text.strip()
        norm_text = re.sub(r'\b([a-zA-Z])\s+(\d+)\b', r'\1\2', clean_text)
        stopwords = {'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'da', 'in', 'con', 'su', 'per', 'del', 'della', 'dei', 'degli', 'a'}
        raw_words = [w for w in re.split(r'[\s%]+', norm_text) if w]
        words = [w for w in raw_words if w.lower() not in stopwords]
        if not words and raw_words:
            words = raw_words
            
        word_conds = []
        for w in words:
            w_lower = w.lower()
            patterns = [f"%{w}%"]
            m = re.match(r'^([a-zA-Z]+)(\d+)$', w)
            if m:
                l, n = m.group(1), m.group(2)
                patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])
                
            w_pats = []
            for pat in patterns:
                w_pats.append(model_item.description.ilike(pat))
                if hasattr(model_item, 'code'):
                    w_pats.append(model_item.code.ilike(pat))
                if hasattr(model_item, 'customer_code'):
                    w_pats.append(model_item.customer_code.ilike(pat))
                if hasattr(model_item, 'raw_code'):
                    w_pats.append(model_item.raw_code.ilike(pat))
                    
            # Sinonimi tecnici: ingranaggio <-> pignone
            if w_lower in ('ingranaggio', 'ingranaggi'):
                w_pats.append(model_item.description.ilike('%pignon%'))
            elif w_lower in ('pignone', 'pignoni'):
                w_pats.append(model_item.description.ilike('%ingranagg%'))
                
            word_conds.append(or_(*w_pats))
            
        return and_(*word_conds) if word_conds else None

    # =========================================================================
    # STRUMENTI (TOOLS / FUNCTION CALLING) ESPOSTI A GEMINI (THREAD-SAFE)
    # =========================================================================

    def cerca_esploso_macchina(self, ricambio: str = "", modello_macchina: str = "", posizione: str = "", limite: int = 15) -> str:
        """
        Cerca tra le tavole d'assieme e gli esplosi tecnici PDF delle macchine di Officina Angeleri (MAV 3150, ICT 60, ECOL, TERMO, ecc.).
        Permette di trovare:
        - In quale esploso compare un ricambio (per codice master es. L011-0096, per vecchio codice da disegno o per descrizione es. 'perno rullo')
        - A quale posizione/pallinatura numerica si trova il pezzo nella macchina
        - Tutti i componenti e le tavole disponibili per una determinata macchina (es. 'ICT 60 mini', 'MAV 3150')
        - Il link cliccabile per aprire direttamente il file PDF a tutto schermo
        """
        from app.database import ExplodedDiagram, ExplodedDiagramItem
        from sqlalchemy.orm import joinedload
        session = get_db_session()
        try:
            query = session.query(ExplodedDiagramItem).join(ExplodedDiagram).options(joinedload(ExplodedDiagramItem.diagram))
            
            clean_macchina = modello_macchina.strip() if modello_macchina else ""
            clean_ricambio = ricambio.strip() if ricambio else ""
            clean_pos = posizione.strip() if posizione else ""
            
            if clean_macchina:
                query = query.filter(
                    (ExplodedDiagram.machine_model.ilike(f"%{clean_macchina}%")) |
                    (ExplodedDiagram.title.ilike(f"%{clean_macchina}%")) |
                    (ExplodedDiagram.code.ilike(f"%{clean_macchina}%"))
                )
                
            if clean_pos:
                query = query.filter(
                    (ExplodedDiagramItem.position_num == clean_pos) |
                    (ExplodedDiagramItem.old_position_code == clean_pos) |
                    (ExplodedDiagramItem.old_position_code.ilike(f"%{clean_pos}%"))
                )
                
            if clean_ricambio:
                s = f"%{clean_ricambio}%"
                query = query.filter(
                    (ExplodedDiagramItem.part_code.ilike(s)) |
                    (ExplodedDiagramItem.description.ilike(s)) |
                    (ExplodedDiagramItem.old_position_code.ilike(s))
                )
                
            items = query.order_by(ExplodedDiagram.machine_model, ExplodedDiagramItem.position_num).limit(limite).all()
            
            results = []
            for it in items:
                diag = it.diagram
                results.append({
                    'macchina': diag.machine_model or 'Officina',
                    'tavola_codice': diag.code,
                    'titolo_esploso': diag.title,
                    'posizione_disegno': it.position_num or it.old_position_code or '-',
                    'codice_master': it.part_code or '-',
                    'descrizione': it.description,
                    'quantita': float(it.quantity or 1.0),
                    'pagina_pdf': it.page_number,
                    'file_pdf': diag.file_name,
                    'link_apertura_pdf': f"app:diagram:{diag.id}"
                })
                
            # Se nessun componente trovato ma è stata specificata una macchina, cerca se esistono tavole generali
            if not results and clean_macchina:
                diags = session.query(ExplodedDiagram).filter(
                    (ExplodedDiagram.machine_model.ilike(f"%{clean_macchina}%")) |
                    (ExplodedDiagram.title.ilike(f"%{clean_macchina}%"))
                ).limit(10).all()
                for d in diags:
                    results.append({
                        'macchina': d.machine_model,
                        'tavola_codice': d.code,
                        'titolo_esploso': d.title,
                        'posizione_disegno': 'Generale',
                        'codice_master': '-',
                        'descrizione': f"Tavola completa {d.title} ({d.pages_count} pag.)",
                        'quantita': 1.0,
                        'pagina_pdf': 1,
                        'file_pdf': d.file_name,
                        'link_apertura_pdf': f"app:diagram:{d.id}"
                    })
                    
            if not results:
                return json.dumps({
                    'messaggio': f"Nessun componente o disegno trovato per ricambio='{clean_ricambio}', macchina='{clean_macchina}'."
                }, ensure_ascii=False)
                
            return json.dumps(results, ensure_ascii=False)
        finally:
            session.close()

    def elenco_fatture(self, soggetto: str = "", tipo: str = "auto", anno: int = None, limite: int = 10, articolo: str = "") -> str:
        """
        Cerca ed elenca le fatture (vendite ai clienti o acquisti dai fornitori).
        FONDAMENTALE:
        - Se 'articolo' non è specificato (es. 'ultime 3 fatture euromarche', 'fatture di IEN', 'fatture 2024'):
          restituisce ESATTAMENTE UNA SOLA RIGA PER CIASCUNA FATTURA (senza ripetere la fattura per ogni articolo),
          con numero fattura, anno, data, soggetto (cliente o fornitore), totale documento (€), numero articoli contenuti e descrizione del primo articolo.
        - Se invece è specificato un 'articolo' (es. 'fatture con rullo morbido'):
          cerca le fatture contenenti quel particolare articolo e restituisce le righe articolo pertinenti.
        - Cerca in modo intelligente sia tra i clienti che tra i fornitori (es. 'Euromarche' è un cliente storico con decine di fatture).
        """
        from app.database import SalesInvoice, SalesInvoiceItem, Customer, Invoice, InvoiceItem, Supplier
        session = get_db_session()
        try:
            results = []
            clean_subj = soggetto.strip() if soggetto else ""
            tipo_norm = tipo.lower().strip() if tipo else "auto"

            matched_customers = self._find_matching_customers(session, clean_subj) if clean_subj else []
            matched_suppliers = self._find_matching_suppliers(session, clean_subj) if clean_subj else []
            cust_ids = [c.id for c in matched_customers]
            supp_ids = [s.id for s in matched_suppliers]

            # 1. CASO RICERCA CON ARTICOLO SPECIFICO
            if articolo and articolo.strip():
                if tipo_norm in ("auto", "vendita", "clienti", "cliente"):
                    q = session.query(SalesInvoiceItem).join(SalesInvoice).outerjoin(Customer, SalesInvoice.customer_id == Customer.id)
                    if cust_ids:
                        q = q.filter(SalesInvoice.customer_id.in_(cust_ids))
                    elif clean_subj:
                        q = q.filter(Customer.name.ilike(f"%{clean_subj}%"))
                    if anno:
                        q = q.filter(SalesInvoice.year == int(anno))
                    cond_art = self._build_item_search_conditions(SalesInvoiceItem, articolo)
                    if cond_art is not None:
                        q = q.filter(cond_art)
                    for it in q.order_by(SalesInvoice.date.desc()).limit(limite).all():
                        results.append({
                            'tipo': 'vendita_cliente',
                            'fattura': str(it.invoice.number),
                            'anno': it.invoice.year,
                            'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                            'soggetto': it.invoice.customer.name if it.invoice.customer else '-',
                            'codice_articolo': it.raw_code or '-',
                            'descrizione_articolo': it.description,
                            'quantita': float(it.quantity or 0.0),
                            'prezzo_unitario': float(it.unit_price or 0.0),
                            'totale_riga': float(it.total_price or 0.0),
                            'totale_fattura': float(it.invoice.total_amount or 0.0),
                            'link_apertura': f"app:invoice:sale:{it.invoice.number}:{it.invoice.year}"
                        })
                if tipo_norm in ("auto", "acquisto", "fornitori", "fornitore"):
                    q = session.query(InvoiceItem).join(Invoice).outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
                    if supp_ids:
                        q = q.filter(Invoice.supplier_id.in_(supp_ids))
                    elif clean_subj:
                        q = q.filter(Supplier.name.ilike(f"%{clean_subj}%"))
                    if anno:
                        q = q.filter(Invoice.date >= f"{anno}-01-01", Invoice.date <= f"{anno}-12-31")
                    cond_art = self._build_item_search_conditions(InvoiceItem, articolo)
                    if cond_art is not None:
                        q = q.filter(cond_art)
                    for it in q.order_by(Invoice.date.desc()).limit(limite).all():
                        results.append({
                            'tipo': 'acquisto_fornitore',
                            'fattura': str(it.invoice.number),
                            'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                            'soggetto': it.invoice.supplier.name if it.invoice.supplier else '-',
                            'codice_articolo': it.code or (it.customer_code or '-'),
                            'descrizione_articolo': it.description,
                            'quantita': float(it.quantity or 0.0),
                            'prezzo_unitario': float(it.unit_price or 0.0),
                            'totale_riga': float(it.total_price or 0.0),
                            'totale_fattura': float(it.invoice.total_amount or 0.0),
                            'link_apertura': f"app:invoice:purchase:{it.invoice.number}"
                        })
                return json.dumps(results[:limite], ensure_ascii=False)

            # 2. CASO ELENCO FATTURE GENERALE (1 RIGA PER FATTURA)
            if tipo_norm in ("auto", "vendita", "clienti", "cliente"):
                from sqlalchemy.orm import joinedload as _jl
                q_inv = session.query(SalesInvoice).outerjoin(Customer, SalesInvoice.customer_id == Customer.id)\
                    .options(_jl(SalesInvoice.items), _jl(SalesInvoice.customer))
                if cust_ids:
                    q_inv = q_inv.filter(SalesInvoice.customer_id.in_(cust_ids))
                elif clean_subj:
                    q_inv = q_inv.filter(Customer.name.ilike(f"%{clean_subj}%"))
                if anno:
                    q_inv = q_inv.filter(SalesInvoice.year == int(anno))
                invs = q_inv.order_by(SalesInvoice.date.desc(), SalesInvoice.number.desc()).limit(limite).all()
                for inv in invs:
                    first_item = inv.items[0].description if inv.items else "-"
                    results.append({
                        'tipo': 'vendita_cliente',
                        'fattura': str(inv.number),
                        'anno': inv.year,
                        'data': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                        'soggetto': inv.customer.name if inv.customer else '-',
                        'totale_documento': float(inv.total_amount or 0.0),
                        'numero_articoli': len(inv.items),
                        'primo_articolo': first_item,
                        'link_apertura': f"app:invoice:sale:{inv.number}:{inv.year}"
                    })

            if tipo_norm in ("auto", "acquisto", "fornitori", "fornitore"):
                if not results or tipo_norm == "acquisto" or not clean_subj or supp_ids:
                    q_inv = session.query(Invoice).outerjoin(Supplier, Invoice.supplier_id == Supplier.id)\
                        .options(_jl(Invoice.items), _jl(Invoice.supplier))
                    if supp_ids:
                        q_inv = q_inv.filter(Invoice.supplier_id.in_(supp_ids))
                    elif clean_subj:
                        q_inv = q_inv.filter(Supplier.name.ilike(f"%{clean_subj}%"))
                    if anno:
                        q_inv = q_inv.filter(Invoice.date >= f"{anno}-01-01", Invoice.date <= f"{anno}-12-31")
                    invs = q_inv.order_by(Invoice.date.desc(), Invoice.number.desc()).limit(limite).all()
                    for inv in invs:
                        first_item = inv.items[0].description if inv.items else "-"
                        results.append({
                            'tipo': 'acquisto_fornitore',
                            'fattura': str(inv.number),
                            'data': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                            'soggetto': inv.supplier.name if inv.supplier else '-',
                            'totale_documento': float(inv.total_amount or 0.0),
                            'numero_articoli': len(inv.items),
                            'primo_articolo': first_item,
                            'link_apertura': f"app:invoice:purchase:{inv.number}"
                        })

            if not results:
                sugg_cust = session.query(Customer.name).filter(Customer.name.ilike(f"%{clean_subj[:3]}%")).limit(5).all() if len(clean_subj) >= 3 else []
                sugg_supp = session.query(Supplier.name).filter(Supplier.name.ilike(f"%{clean_subj[:3]}%")).limit(5).all() if len(clean_subj) >= 3 else []
                nomi = [c[0] for c in sugg_cust] + [s[0] for s in sugg_supp]
                return json.dumps({
                    'messaggio': f"Nessuna fattura trovata per '{clean_subj}'.",
                    'suggerimenti_anagrafica': nomi[:5]
                }, ensure_ascii=False)

            return json.dumps(results[:limite], ensure_ascii=False)
        finally:
            session.close()

    def _format_prod_dict(self, p_data: dict) -> dict:
        prod = p_data['product']
        return {
            'codice_master': prod.code,
            'descrizione': prod.name,
            'tipologia': prod.type,
            'categoria': prod.category or "Standard",
            'costo_standard': float(prod.production_cost or 0.0),
            'prezzo_listino': float(prod.list_price or 0.0),
            'codici_legacy_esploso': [
                {'codice': l.legacy_code, 'descrizione': l.legacy_description or ''}
                for l in p_data.get('legacy_codes', [])
            ],
            'fornitori_collegati': [
                {
                    'fornitore': sp.supplier.name if sp.supplier else 'N/D',
                    'codice_fornitore': sp.supplier_code,
                    'descrizione_fornitore': sp.supplier_description or ''
                }
                for sp in p_data.get('supplier_products', [])
            ],
            'ultimi_acquisti': [
                {
                    'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                    'fornitore': it.invoice.supplier.name if it.invoice.supplier else '-',
                    'fattura': it.invoice.number,
                    'quantita': float(it.quantity or 0),
                    'prezzo_unitario': float(it.unit_price or 0.0)
                }
                for it in p_data.get('recent_purchases', [])[:5]
            ],
            'ultime_vendite': [
                {
                    'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                    'cliente': it.invoice.customer.name if it.invoice.customer else '-',
                    'fattura': str(it.invoice.number),
                    'quantita': float(it.quantity or 0),
                    'prezzo_unitario': float(it.unit_price or 0.0)
                }
                for it in p_data.get('recent_sales', [])[:5]
            ]
        }

    def cerca_tutti_articoli(self, ricerca: str, limite: int = 35) -> str:
        """
        Cerca e restituisce tutti gli articoli del catalogo officina che contengono le parole chiave indicate nella descrizione o nel codice.
        Da usare specificamente quando l'utente chiede 'tutti i rulli superiori che trovi', 'elenco dei pignoni', 'quali ingranaggi ci sono', ecc.
        Restituisce una lista completa con codice master, descrizione, categoria, costo standard, prezzo listino e codici esploso legacy.
        """
        session = get_db_session()
        try:
            from app.database import Product, ProductLegacyCode
            clean = ricerca.strip().replace('\u200b', '')
            if not clean:
                return json.dumps([])

            stop_words = {'dazn', 'da', 'di', 'del', 'della', 'dei', 'degli', 'in', 'il', 'la', 'le', 'un', 'una', 'e', 'ed', 'con', 'per', 'tutti', 'tutto', 'trovi', 'elenco', 'mostra', 'cerca'}
            words = [w.strip() for w in clean.split() if len(w.strip()) > 1 and w.strip().lower() not in stop_words]

            q = session.query(Product)
            if words:
                from sqlalchemy import or_
                import re
                for w in words:
                    w_lower = w.lower()
                    patterns = [f"%{w}%"]
                    m = re.match(r'^([a-zA-Z]+)(\d+)$', w)
                    if m:
                        l, n = m.group(1), m.group(2)
                        patterns.extend([f"%{l} {n}%", f"%{l}={n}%", f"%{l}.{n}%", f"%{l}-{n}%"])
                    w_conds = []
                    for pat in patterns:
                        w_conds.append(Product.name.ilike(pat))
                        w_conds.append(Product.code.ilike(pat))
                    if w_lower in ('ingranaggio', 'ingranaggi'):
                        w_conds.append(Product.name.ilike('%pignon%'))
                    elif w_lower in ('pignone', 'pignoni'):
                        w_conds.append(Product.name.ilike('%ingranagg%'))
                    q = q.filter(or_(*w_conds))
            else:
                q = q.filter(Product.name.ilike(f"%{clean}%"))

            prods = q.order_by(Product.code.asc()).limit(limite).all()
            results = []
            for p in prods:
                legs = [l.legacy_code for l in session.query(ProductLegacyCode).filter_by(product_id=p.id).all()]
                results.append({
                    'codice_master': p.code,
                    'descrizione': p.name,
                    'categoria': p.category or 'Standard',
                    'costo_standard': float(p.production_cost or 0.0),
                    'prezzo_listino': float(p.list_price or 0.0),
                    'codici_esploso_legacy': legs
                })
            return json.dumps(results, ensure_ascii=False)
        finally:
            session.close()

    def cerca_ricambio_360(self, termine: str) -> str:
        """
        Cerca la scheda tecnica e commerciale completa (360°) di un ricambio nel catalogo di Officina Angeleri.
        Accetta un codice master (es. A850-0050, L010-0001), un codice vecchio da esploso (es. 3150-12, 00ICT60-01), 
        un codice fornitore o una descrizione (es. 'rullo morbido', 'motore carpanelli').
        Restituisce costi, listini, equivalenze fornitori e storico acquisti/vendite.
        """
        session = get_db_session()
        try:
            from app.database import Product, ProductLegacyCode, SupplierProduct, Supplier, InvoiceItem, Invoice, SalesInvoiceItem, SalesInvoice
            clean = termine.strip().replace('\u200b', '')
            if not clean:
                return json.dumps({"errore": "Termine di ricerca vuoto."})

            # 1. Ricerca codice esatto
            prod = session.query(Product).filter(Product.code.ilike(clean)).first()
            if not prod:
                leg = session.query(ProductLegacyCode).filter(ProductLegacyCode.legacy_code.ilike(clean)).first()
                if leg: prod = leg.product
            if not prod:
                sp = session.query(SupplierProduct).filter(SupplierProduct.supplier_code.ilike(clean)).first()
                if sp: prod = sp.product
            # 2. Ricerca per codice parziale
            if not prod:
                prod = session.query(Product).filter(Product.code.ilike(f"%{clean}%")).first()
            # 3. Ricerca per nome esatto/parziale del prodotto master (priorità rispetto alle descrizioni secondarie!)
            if not prod:
                prod = session.query(Product).filter(Product.name.ilike(f"%{clean}%")).first()
            # 4. Ricerca per codice esploso legacy parziale
            if not prod:
                leg = session.query(ProductLegacyCode).filter(ProductLegacyCode.legacy_code.ilike(f"%{clean}%")).first()
                if leg: prod = leg.product
            # 5. Ricerca per descrizione secondaria esploso legacy
            if not prod:
                leg = session.query(ProductLegacyCode).filter(ProductLegacyCode.legacy_description.ilike(f"%{clean}%")).first()
                if leg: prod = leg.product
            # 6. Ricerca multi-parola
            if not prod and len(clean.split()) > 1:
                stop_words = {'da', 'di', 'del', 'della', 'dei', 'in', 'il', 'la', 'un', 'una', 'e', 'per', 'con'}
                words = [w for w in clean.split() if len(w) > 2 and w.lower() not in stop_words]
                if words:
                    # Prima cerchiamo nei nomi dei prodotti master
                    q = session.query(Product)
                    for w in words:
                        q = q.filter((Product.name.ilike(f"%{w}%")) | (Product.code.ilike(f"%{w}%")))
                    prod = q.first()
                    
                    # Se ancora non trovato, proviamo con le tabelle fornitore e legacy
                    if not prod:
                        q2 = session.query(Product)\
                            .outerjoin(SupplierProduct, Product.id == SupplierProduct.product_id)\
                            .outerjoin(Supplier, SupplierProduct.supplier_id == Supplier.id)\
                            .outerjoin(ProductLegacyCode, Product.id == ProductLegacyCode.product_id)
                        for w in words:
                            q2 = q2.filter(
                                (Product.name.ilike(f"%{w}%")) |
                                (Product.code.ilike(f"%{w}%")) |
                                (Supplier.name.ilike(f"%{w}%")) |
                                (SupplierProduct.supplier_code.ilike(f"%{w}%")) |
                                (SupplierProduct.supplier_description.ilike(f"%{w}%")) |
                                (ProductLegacyCode.legacy_code.ilike(f"%{w}%")) |
                                (ProductLegacyCode.legacy_description.ilike(f"%{w}%"))
                            )
                        prod = q2.first()

            if not prod:
                return json.dumps({"errore": f"Nessun ricambio trovato corrispondente a '{termine}'."})

            legacy_codes = session.query(ProductLegacyCode).filter_by(product_id=prod.id).all()
            supplier_products = session.query(SupplierProduct).filter_by(product_id=prod.id).all()
            recent_purchases = (session.query(InvoiceItem).join(Invoice)
                                .filter(InvoiceItem.product_id == prod.id)
                                .order_by(Invoice.date.desc()).limit(5).all())
            recent_sales = (session.query(SalesInvoiceItem).join(SalesInvoice)
                            .filter(SalesInvoiceItem.product_id == prod.id)
                            .order_by(SalesInvoice.date.desc()).limit(5).all())

            p_data = {
                'product': prod,
                'legacy_codes': legacy_codes,
                'supplier_products': supplier_products,
                'recent_purchases': recent_purchases,
                'recent_sales': recent_sales
            }
            return json.dumps(self._format_prod_dict(p_data), ensure_ascii=False)
        finally:
            session.close()

    def confronta_elenco_ricambi(self, lista_ricambi: list[str]) -> str:
        """
        Confronta simultaneamente un elenco di ricambi forniti dall'utente.
        Da usare specificamente quando l'utente chiede 'Cerca i prezzi di X, poi di Y e poi di Z' o vuole una comparazione su più articoli.
        Restituisce la scheda completa per ciascun articolo dell'elenco.
        """
        results = []
        for term in lista_ricambi:
            res_str = self.cerca_ricambio_360(term)
            try:
                data = json.loads(res_str)
                results.append(data)
            except Exception:
                results.append({"ricerca": term, "stato": "Errore lettura"})
        return json.dumps(results, ensure_ascii=False)

    def dettaglio_completo_fattura(self, numero_fattura: str, anno: int = 0, tipo: str = "auto", cliente_o_fornitore: str = "") -> str:
        """
        Recupera tutti i dati e l'elenco completo delle righe articolo di una specifica fattura (di vendita a cliente o di acquisto da fornitore).
        Da usare specificamente quando l'utente chiede 'apri la fattura 217', 'mostrami tutta la fattura 217', 'cosa contiene la fattura 217', ecc.
        Restituisce testata, cliente/fornitore, data, totale documento e tutte le righe articolo con quantità, prezzi e sconti.
        """
        from app.database import SalesInvoice, SalesInvoiceItem, Invoice, InvoiceItem, Customer, Supplier
        session = get_db_session()
        try:
            clean_num = str(numero_fattura).strip()
            inv_sale = None
            inv_pur = None

            # Cerca nelle fatture clienti
            if tipo in ("vendita", "auto"):
                q_sale = session.query(SalesInvoice).filter(SalesInvoice.number == clean_num)
                if anno:
                    q_sale = q_sale.filter(SalesInvoice.year == int(anno))
                if cliente_o_fornitore:
                    matched_c = self._find_matching_customers(session, cliente_o_fornitore)
                    if matched_c:
                        q_sale = q_sale.filter(SalesInvoice.customer_id.in_([c.id for c in matched_c]))
                    else:
                        q_sale = q_sale.join(Customer).filter(Customer.name.ilike(f"%{cliente_o_fornitore.strip()}%"))
                inv_sale = q_sale.order_by(SalesInvoice.date.desc()).first()

            # Cerca nelle fatture fornitori se non trovata tra i clienti o se tipo è acquisto
            if not inv_sale and tipo in ("acquisto", "fornitore", "auto"):
                q_pur = session.query(Invoice).filter(Invoice.number == clean_num)
                if cliente_o_fornitore:
                    matched_s = self._find_matching_suppliers(session, cliente_o_fornitore)
                    if matched_s:
                        q_pur = q_pur.filter(Invoice.supplier_id.in_([s.id for s in matched_s]))
                    else:
                        q_pur = q_pur.join(Supplier).filter(Supplier.name.ilike(f"%{cliente_o_fornitore.strip()}%"))
                inv_pur = q_pur.order_by(Invoice.date.desc()).first()

            if inv_sale:
                items = [
                    {
                        'riga': it.line_number or (i + 1),
                        'codice': it.raw_code or '-',
                        'descrizione': it.description,
                        'unita_misura': it.unit_measure or 'NR',
                        'quantita': float(it.quantity or 0),
                        'prezzo_unitario': float(it.unit_price or 0.0),
                        'sconto': float(it.discount or 0.0),
                        'totale_riga': float(it.total_price or 0.0)
                    }
                    for i, it in enumerate(inv_sale.items)
                ]
                return json.dumps({
                    'tipo': 'vendita_cliente',
                    'id_fattura': inv_sale.id,
                    'numero': inv_sale.number,
                    'anno': inv_sale.year,
                    'data': inv_sale.date.strftime('%d/%m/%Y') if inv_sale.date else '-',
                    'cliente': inv_sale.customer.name if inv_sale.customer else 'N/D',
                    'piva': inv_sale.customer.piva_cf or '-',
                    'indirizzo': inv_sale.customer.address or '-',
                    'tipo_documento': inv_sale.doc_type or 'Fattura Differita',
                    'totale_documento': float(inv_sale.total_amount or 0.0),
                    'file_sorgente': inv_sale.file_path or '-',
                    'righe': items,
                    'link_apertura': f"app:invoice:sale:{inv_sale.number}:{inv_sale.year}"
                }, ensure_ascii=False)

            if inv_pur:
                items = [
                    {
                        'riga': i + 1,
                        'codice': it.code or (it.customer_code or '-'),
                        'descrizione': it.description,
                        'quantita': float(it.quantity or 0),
                        'prezzo_unitario': float(it.unit_price or 0.0),
                        'totale_riga': float(it.total_price or 0.0)
                    }
                    for i, it in enumerate(inv_pur.items)
                ]
                return json.dumps({
                    'tipo': 'acquisto_fornitore',
                    'id_fattura': inv_pur.id,
                    'numero': inv_pur.number,
                    'data': inv_pur.date.strftime('%d/%m/%Y') if inv_pur.date else '-',
                    'fornitore': inv_pur.supplier.name if inv_pur.supplier else 'N/D',
                    'piva': inv_pur.supplier.piva or '-',
                    'totale_documento': float(inv_pur.total_amount or 0.0),
                    'file_sorgente': inv_pur.file_path or '-',
                    'righe': items,
                    'link_apertura': f"app:invoice:purchase:{inv_pur.number}"
                }, ensure_ascii=False)

            return json.dumps({'errore': f"Fattura n. '{clean_num}' non trovata nell'archivio."})
        finally:
            session.close()

    def storico_prezzi_fornitore(self, fornitore: str = "", articolo: str = "", limite: int = 15) -> str:
        """
        Cerca nello storico delle fatture di acquisto fornitori i prezzi effettivamente pagati dall'officina.
        Può filtrare per nome del fornitore (es. 'IMBG', 'I.M.B.G.', 'Alusic', 'Carpanelli', 'Sacchi') e/o per codice/descrizione articolo.
        """
        from app.database import InvoiceItem, Invoice, Supplier
        session = get_db_session()
        try:
            query = session.query(InvoiceItem).join(Invoice).outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
            if fornitore:
                matched_suppliers = self._find_matching_suppliers(session, fornitore)
                if matched_suppliers:
                    supp_ids = [s.id for s in matched_suppliers]
                    query = query.filter(Invoice.supplier_id.in_(supp_ids))
                else:
                    query = query.filter(Supplier.name.ilike(f"%{fornitore.strip()}%"))
            if articolo:
                cond = self._build_item_search_conditions(InvoiceItem, articolo)
                if cond is not None:
                    query = query.filter(cond)
                
            items = query.order_by(Invoice.date.desc()).limit(limite).all()
            results = [
                {
                    'id_fattura': it.invoice.id,
                    'fornitore': it.invoice.supplier.name if it.invoice.supplier else '-',
                    'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                    'fattura': it.invoice.number,
                    'link_apertura': f"app:invoice:purchase:{it.invoice.number}",
                    'codice': it.code,
                    'descrizione': it.description,
                    'quantita': float(it.quantity or 0),
                    'prezzo_unitario': float(it.unit_price or 0.0),
                    'totale_riga': float(it.total_price or 0.0)
                }
                for it in items
            ]
            return json.dumps(results, ensure_ascii=False)
        finally:
            session.close()

    def storico_vendite_cliente(self, cliente: str = "", articolo: str = "", limite: int = 15) -> str:
        """
        Cerca nello storico delle fatture di vendita ai clienti (2019-2026) i prezzi effettivamente applicati.
        Può filtrare per ragione sociale del cliente e/o per articolo/descrizione.
        """
        from app.database import SalesInvoiceItem, SalesInvoice, Customer
        session = get_db_session()
        try:
            query = session.query(SalesInvoiceItem).join(SalesInvoice).outerjoin(Customer, SalesInvoice.customer_id == Customer.id)
            if cliente:
                matched_customers = self._find_matching_customers(session, cliente)
                if matched_customers:
                    cust_ids = [c.id for c in matched_customers]
                    query = query.filter(SalesInvoice.customer_id.in_(cust_ids))
                else:
                    query = query.filter(Customer.name.ilike(f"%{cliente.strip()}%"))
            if articolo:
                cond = self._build_item_search_conditions(SalesInvoiceItem, articolo)
                if cond is not None:
                    query = query.filter(cond)
                
            items = query.order_by(SalesInvoice.date.desc()).limit(limite).all()
            results = [
                {
                    'id_fattura': it.invoice.id,
                    'cliente': it.invoice.customer.name if it.invoice.customer else '-',
                    'data': it.invoice.date.strftime('%d/%m/%Y') if it.invoice.date else '-',
                    'anno': it.invoice.year,
                    'fattura': str(it.invoice.number),
                    'link_apertura': f"app:invoice:sale:{it.invoice.number}:{it.invoice.year}",
                    'codice': it.raw_code,
                    'descrizione': it.description,
                    'quantita': float(it.quantity or 0),
                    'prezzo_vendita': float(it.unit_price or 0.0),
                    'sconto': float(it.discount or 0.0)
                }
                for it in items
            ]
            return json.dumps(results, ensure_ascii=False)
        finally:
            session.close()

    def dettaglio_fornitore(self, nome_fornitore: str) -> str:
        """
        Restituisce la scheda di un fornitore con P.IVA, totale fatturato/speso, numero fatture e elenco articoli forniti.
        """
        from app.database import Supplier, Invoice, SupplierProduct
        session = get_db_session()
        try:
            matched_suppliers = self._find_matching_suppliers(session, nome_fornitore)
            s = matched_suppliers[0] if matched_suppliers else None
            if not s:
                return json.dumps({"errore": f"Fornitore '{nome_fornitore}' non trovato."})
            invoices = session.query(Invoice).filter_by(supplier_id=s.id)\
                .options(__import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(Invoice.items))\
                .order_by(Invoice.date.desc()).all()
            products = session.query(SupplierProduct).filter_by(supplier_id=s.id).all()
            tot_spent = sum(inv.total_amount for inv in invoices)
            
            return json.dumps({
                'nome': s.name,
                'piva': s.piva or '-',
                'totale_speso': float(tot_spent),
                'numero_fatture': len(invoices),
                'ultima_fattura': invoices[0].date.strftime('%d/%m/%Y') if invoices and invoices[0].date else '-',
                'ultime_fatture': [
                    {
                        'fattura': inv.number,
                        'data': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                        'totale': float(inv.total_amount or 0.0),
                        'numero_articoli': len(inv.items),
                        'primo_articolo': inv.items[0].description if inv.items else '-',
                        'link_apertura': f"app:invoice:purchase:{inv.number}"
                    }
                    for inv in invoices[:5]
                ],
                'numero_articoli_forniti': len(products),
                'primi_articoli_catalogo': [
                    {'codice_fornitore': p.supplier_code, 'codice_interno': p.product.code if p.product else '-', 'desc': p.supplier_description or (p.product.name if p.product else '')}
                    for p in products[:15]
                ]
            }, ensure_ascii=False)
        finally:
            session.close()

    def dettaglio_cliente(self, nome_cliente: str) -> str:
        """
        Restituisce la scheda di un cliente con totale vendite, numero fatture emesse, ultimi acquisti e ultime fatture.
        """
        from app.database import Customer, SalesInvoice
        session = get_db_session()
        try:
            matched_customers = self._find_matching_customers(session, nome_cliente)
            c = matched_customers[0] if matched_customers else None
            if not c:
                return json.dumps({"errore": f"Cliente '{nome_cliente}' non trovato."})
            invoices = session.query(SalesInvoice).filter_by(customer_id=c.id)\
                .options(__import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(SalesInvoice.items))\
                .order_by(SalesInvoice.date.desc()).all()
            tot_billed = sum(inv.total_amount for inv in invoices)
            
            return json.dumps({
                'nome': c.name,
                'piva': getattr(c, 'piva_cf', '-') or getattr(c, 'piva', '-'),
                'totale_fatturato': float(tot_billed),
                'numero_fatture': len(invoices),
                'ultima_fattura': invoices[0].date.strftime('%d/%m/%Y') if invoices and invoices[0].date else '-',
                'ultime_fatture': [
                    {
                        'fattura': str(inv.number),
                        'anno': inv.year,
                        'data': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                        'totale': float(inv.total_amount or 0.0),
                        'numero_articoli': len(inv.items),
                        'primo_articolo': inv.items[0].description if inv.items else '-',
                        'link_apertura': f"app:invoice:sale:{inv.number}:{inv.year}"
                    }
                    for inv in invoices[:5]
                ]
            }, ensure_ascii=False)
        finally:
            session.close()

    def statistiche_generali_officina(self) -> str:
        """
        Restituisce un quadro generale dell'officina: totale fatturato clienti, totale acquisti fornitori, 
        i 5 principali fornitori per spesa e i 5 principali clienti per fatturato.
        """
        from sqlalchemy import func, desc
        from app.database import Invoice, InvoiceItem, SalesInvoice, Customer

        session = get_db_session()
        try:
            total_purchases_net = session.query(func.sum(InvoiceItem.total_price)).scalar() or 0.0
            total_purchases_count = session.query(Invoice).count()

            # Top 5 fornitori
            inv_by_supp = {}
            for inv in session.query(Invoice).all():
                s_name = inv.supplier.name if inv.supplier else "N/D"
                inv_by_supp[s_name] = inv_by_supp.get(s_name, 0.0) + (inv.total_amount or 0.0)
            top_supp = [
                {'fornitore': name, 'spesa': float(tot)}
                for name, tot in sorted(inv_by_supp.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
            
            # Statistiche vendite clienti
            tot_sales = session.query(func.sum(SalesInvoice.total_amount)).scalar() or 0.0
            tot_sales_count = session.query(SalesInvoice).count()

            top_cust_query = session.query(
                Customer.name,
                func.sum(SalesInvoice.total_amount).label('tot_fatturato')
            ).join(SalesInvoice, Customer.id == SalesInvoice.customer_id)\
             .group_by(Customer.id)\
             .order_by(desc('tot_fatturato'))\
             .limit(5).all()

            top_cust = [
                {'cliente': name, 'fatturato': float(tot)}
                for name, tot in top_cust_query
            ]

            return json.dumps({
                'totale_fatturato_vendite_clienti': float(tot_sales),
                'numero_fatture_vendita': tot_sales_count,
                'totale_acquisti_fornitori': float(total_purchases_net),
                'numero_fatture_acquisto': total_purchases_count,
                'top_5_fornitori': top_supp,
                'top_5_clienti': top_cust
            }, ensure_ascii=False)
        finally:
            session.close()

    def calcola_costo_produzione(self, codice_articolo: str) -> str:
        """
        Calcola e restituisce la distinta base (materiali/componenti) e il ciclo di lavorazione con ore macchina e attrezzaggio per un articolo di produzione (es. L010-0016).
        Restituisce la composizione dettagliata dei costi, il totale materiali, il totale ore lavorazione e il costo finale stimato per pezzo.
        """
        res = self.controller.calculate_production_piece_cost(codice_articolo)
        return json.dumps(res, ensure_ascii=False)

    def calcola_spezzone_materiale(self, codice_materiale: str, lunghezza_mm: float) -> str:
        """
        Calcola il peso e il costo di uno spezzone di materiale commerciale (es. barra di ottone A102-0008, tondo alluminio, piastra, profilo)
        a partire dalla lunghezza richiesta in millimetri (es. 200 mm), applicando il fattore di conversione lunghezza -> peso (kg/m) e l'ultimo prezzo di acquisto al kg.
        """
        res = self.controller.calculate_raw_material_cut(codice_materiale, float(lunghezza_mm))
        return json.dumps(res, ensure_ascii=False)

