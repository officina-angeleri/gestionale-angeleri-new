import xml.etree.ElementTree as ET
import re
from datetime import datetime
from typing import List
from .base import InvoiceParser, ParsedInvoice, ParsedInvoiceItem

class XMLSDIInvoiceParser(InvoiceParser):
    def can_handle(self, file_path: str) -> bool:
        return file_path.lower().endswith('.xml')

    def parse(self, file_path: str) -> List[ParsedInvoice]:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except Exception as e:
            # Potrebbe essere un file .xml non valido o con encoding problematico
            print(f"Errore parsing XML {file_path}: {e}")
            return []
        
        # Gestione namespace flessibile
        # In SdI XML i namespace sono solitamente nel root come xmlns:p="http://..."
        # Usiamo {url}Tag per cercarli o registriamo il prefisso ns.
        ns_url = ""
        if '}' in root.tag:
            ns_url = root.tag.split('}')[0].strip('{')
        
        ns = {'ns': ns_url} if ns_url else {}

        def get_local_name(tag):
            return tag.split('}')[-1]

        def find_tag(parent, tag_path):
            # Prova ricorsiva con namespace se presente
            if ns:
                path_parts = tag_path.split('/')
                ns_path = ".//" + "/".join([f'ns:{p}' for p in path_parts])
                res = parent.find(ns_path, ns)
                if res is not None: return res
            
            # Fallback senza namespace o cerca per local name
            return parent.find(f".//{tag_path}")

        def find_all_tags(parent, tag_path):
            if ns:
                path_parts = tag_path.split('/')
                ns_path = ".//" + "/".join([f'ns:{p}' for p in path_parts])
                res = parent.findall(ns_path, ns)
                if res: return res
            
            return parent.findall(f".//{tag_path}")

        invoices = []
        
        # Header (Denominazione Cedente e P.IVA)
        header = find_tag(root, 'FatturaElettronicaHeader')
        supplier_name = "Sconosciuto"
        supplier_piva = ""
        if header is not None:
            cedente = find_tag(header, 'CedentePrestatore')
            if cedente is not None:
                # Estrazione P.IVA o Codice Fiscale
                id_codice = find_tag(cedente, 'DatiAnagrafici/IdFiscaleIVA/IdCodice')
                if id_codice is not None and id_codice.text:
                    supplier_piva = id_codice.text.strip()
                if not supplier_piva:
                    cf = find_tag(cedente, 'DatiAnagrafici/CodiceFiscale')
                    if cf is not None and cf.text:
                        supplier_piva = cf.text.strip()

                denom = find_tag(cedente, 'DatiAnagrafici/Anagrafica/Denominazione')
                if denom is not None and denom.text:
                    supplier_name = " ".join(denom.text.split())
                else:
                    nome = find_tag(cedente, 'DatiAnagrafici/Anagrafica/Nome')
                    cognome = find_tag(cedente, 'DatiAnagrafici/Anagrafica/Cognome')
                    if nome is not None and cognome is not None:
                        n_str = nome.text.strip() if nome.text else ""
                        c_str = cognome.text.strip() if cognome.text else ""
                        supplier_name = " ".join(f"{n_str} {c_str}".split())

        bodies = find_all_tags(root, 'FatturaElettronicaBody')
        for body in bodies:
            dati_generali = find_tag(body, 'DatiGenerali/DatiGeneraliDocumento')
            if dati_generali is None: continue
            
            num_tag = find_tag(dati_generali, 'Numero')
            date_tag = find_tag(dati_generali, 'Data')
            if num_tag is None or date_tag is None: continue
            
            number = num_tag.text.strip()
            date_str = date_tag.text.strip()
            try:
                inv_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                inv_date = datetime.now().date()
            
            total_tag = find_tag(dati_generali, 'ImportoTotaleDocumento')
            total_amount = float(total_tag.text.strip()) if total_tag is not None else 0.0
            
            items = []
            last_item = None # Per gestire sconti scorporati (es. Alusic)
            linee = find_all_tags(body, 'DatiBeniServizi/DettaglioLinee')
            for linee_el in linee:
                desc_tag = find_tag(linee_el, 'Descrizione')
                desc = desc_tag.text.strip() if desc_tag is not None else "Senza descrizione"
                
                qty_tag = find_tag(linee_el, 'Quantita')
                qty = float(qty_tag.text.strip()) if qty_tag is not None else 1.0
                
                price_tag = find_tag(linee_el, 'PrezzoUnitario')
                price = float(price_tag.text.strip()) if price_tag is not None else 0.0
                
                line_total_tag = find_tag(linee_el, 'PrezzoTotale')
                line_total = float(line_total_tag.text.strip()) if line_total_tag is not None else (qty * price)
                
                # Calcolo Prezzo Unitario REALE (al netto di sconti/maggiorazioni interni alla riga)
                # Questo permette di gestire i tag <ScontoMaggiorazione> nativamente presenti nella riga.
                if abs(qty) > 0.0001:
                    price = line_total / qty

                # Codici Articolo
                code = ""
                customer_code = ""
                # Cerchiamo tutti i <CodiceArticolo>
                codici_art = find_all_tags(linee_el, 'CodiceArticolo')
                for ca in codici_art:
                    c_tipo_tag = find_tag(ca, 'CodiceTipo')
                    c_val_tag = find_tag(ca, 'CodiceValore')
                    if c_tipo_tag is not None and c_val_tag is not None:
                        tipo = c_tipo_tag.text.strip().upper()
                        valore = c_val_tag.text.strip()
                        if tipo in ['ART.', 'CODICE FORNITORE', 'FORNITORE', 'COD', 'INTERNALCODE', 'ASWARTFOR', 'SA', 'MF']:
                            code = valore
                        elif tipo in ['ART.CLI.', 'CODICE CLIENTE', 'CLIENTE', 'ASWARTCLI', 'CU']:
                            customer_code = valore
                
                # Se non abbiamo trovato il codice primario con 'ART.', prendiamo il primo disponibile se presente
                if not code and not customer_code and codici_art:
                    first_val = find_tag(codici_art[0], 'CodiceValore')
                    if first_val is not None: code = first_val.text.strip()

                # === GESTIONE SCONTI SCORPORATI (es. ALUSIC) ===
                # Se la riga è contrassegnata come Sconto (TipoCessionePrestazione SC o descrizione Sconto)
                # e segue un articolo compatibile, incorporiamo lo sconto nell'articolo precedente.
                tipo_cessione = find_tag(linee_el, 'TipoCessionePrestazione')
                is_separate_discount = (tipo_cessione is not None and tipo_cessione.text.strip().upper() == 'SC')
                
                # Fallback: se la descrizione contiene "Sconto" o "Abbuono" e il prezzo è negativo
                if not is_separate_discount and price < 0:
                    upper_desc = desc.upper()
                    if "SCONTO" in upper_desc or "ABBUONO" in upper_desc or "SC." in upper_desc:
                        is_separate_discount = True
                
                if is_separate_discount and last_item:
                    # Verifica compatibilità: stesso codice o codice vuoto nello sconto
                    if not code or code == last_item.code:
                        last_item.total_price += line_total
                        if abs(last_item.quantity) > 0.0001:
                            last_item.unit_price = last_item.total_price / last_item.quantity
                        continue # Salta l'aggiunta di questo item come riga separata
                
                # === FILTRO RIGHE TECNICHE ===
                # Lista di stringhe che identificano righe di metadati/commenti
                technical_noise_keywords = [
                    "riga ausiliaria",
                    "informazioni tecniche",
                    "sconto visualizzato",
                    "omaggio",
                    "ddt num",
                    "contributo conai",
                    "note:"
                ]
                
                # Verifica se la descrizione contiene parole chiave tecniche (case-insensitive)
                is_technical_noise = any(
                    keyword.upper() in desc.upper() 
                    for keyword in technical_noise_keywords
                )
                
                # CONDIZIONI DI SKIP:
                # 1. Se è rumore tecnico E ha prezzo zero -> SKIP
                # 2. Se ha prezzo zero E non ha né codice fornitore né codice cliente -> SKIP
                should_skip = False
                
                if abs(price) < 0.001:  # Prezzo zero o quasi
                    if is_technical_noise:
                        should_skip = True
                    elif not code and not customer_code:
                        should_skip = True
                
                if should_skip:
                    continue  # Salta questa riga, non aggiungerla agli items

                new_item = ParsedInvoiceItem(
                    code=code,
                    customer_code=customer_code,
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    total_price=line_total
                )
                items.append(new_item)
                
                # Se non è rumore tecnico e ha un codice, lo consideriamo come potenziale riga padre
                if not is_technical_noise and code:
                    last_item = new_item
            
            invoices.append(ParsedInvoice(
                supplier_name=supplier_name,
                date=inv_date,
                number=number,
                total_amount=total_amount or sum(i.total_price for i in items),
                items=items,
                original_file_path=file_path,
                supplier_piva=supplier_piva
            ))
            
        return invoices
