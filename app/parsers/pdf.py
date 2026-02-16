import pdfplumber
import re
from datetime import datetime
from typing import List
from .base import InvoiceParser, ParsedInvoice, ParsedInvoiceItem

class PDFInvoiceParser(InvoiceParser):
    def can_handle(self, file_path: str) -> bool:
        return file_path.lower().endswith('.pdf')

    def parse_sdi_layout(self, text: str, file_path: str) -> List[ParsedInvoice]:
        """Parser per layout standard SdI / ERP, gestisce più fatture con stato robusto e precisione elevata."""
        invoices = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        current_header = {'supplier': "Sconosciuto", 'number': None, 'date': None}
        current_items = []
        current_item_data = {}
        buffer_desc = []
        
        def clean_desc_text(t):
            if not t: return ""
            # Pulizia DDT e Riferimenti Temporali
            t = re.sub(r'(?i)\d{4,}/\d{2,}\s+del\s+\d{2}[-/]\d{2}[-/]\d{2,4}', '', t)
            # Pulizia Metadata Tecnici ( wildcards per Descrittivo/Normale e Codici Stato )
            t = re.sub(r'(?i)AswTRiga\s*[:]\s*\w+\s*#\w+#', '', t)
            for s in ["Sconti Aliquota", "Natura Addebiti", "Addebiti Iva %", "Riga Descrizione U.m. Quantit Prezzo Importo Natura", "DdT num.", "fornitore"]:
                t = re.sub(f'(?i){re.escape(s)}', '', t)
            
            # Pulizia Codici
            t = re.sub(r'(?i)\b(ART\.CLI\.|ART\.|AswArtFor|Codice Art\.)\s*[:]?\s*', '', t)
            # Pulizia U.M.
            t = re.sub(r'(?i)\s*\b(PZ|PCE|PCS|M|ML|MT|LMT|KG|GR|NR|SET|PAIA|PZ\.)\b\s*$', '', t)
            return t.strip()

        def save_current_invoice():
            nonlocal current_items, current_header
            if current_items and current_header['number']:
                total = sum(item.total_price for item in current_items)
                try:
                    invoices.append(ParsedInvoice(
                        supplier_name=str(current_header['supplier']),
                        date=current_header['date'] or datetime.now().date(),
                        number=str(current_header['number']),
                        total_amount=float(total),
                        items=list(current_items),
                        original_file_path=str(file_path)
                    ))
                except: pass
            current_items = []

        for i, line in enumerate(lines):
            line_up = line.upper()
            
            # TRIGGER TESTATA / PAGINA
            if any(k in line_up for k in ["FATTURA ELETTRONICA", "CEDENTE / PRESTATORE"]):
                buffer_desc = [] 
                ctx = " ".join(lines[i : i+12])
                n_match = re.search(r'(?i)Numero(?:\s+documento)?\s*:?\s*([\w\d/.-]{6,20})', ctx)
                num = n_match.group(1) if n_match else None
                if not num:
                    m = re.findall(r'\b(\d{4,}/\d{2,10}|\d{10,12})\b', ctx)
                    for c in m:
                        if c not in ["01163890187", "01057080184", "00689730133"]:
                            num = c
                            break

                d_match = re.search(r'(?i)Data(?:\s+documento)?\s*:?\s*(\d{2,4}[-/]\d{2}[-/]\d{2,4})', ctx)
                dt_str = d_match.group(1) if d_match else None
                if not dt_str:
                    dm = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', ctx)
                    if dm: dt_str = dm.group(0)

                if num and dt_str:
                    is_new = num != current_header['number']
                    if is_new:
                        save_current_invoice()
                        current_header['supplier'] = "Sconosciuto"
                        current_header['number'] = num
                        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
                            try:
                                current_header['date'] = datetime.strptime(dt_str, fmt).date()
                                break
                            except: pass

                    if current_header['supplier'] == "Sconosciuto":
                        for j in range(1, 12):
                            if i+j < len(lines):
                                cand = lines[i+j].strip()
                                if any(k in cand.upper() for k in ["SRL", "SPA", "S.R.L.", "S.P.A.", "SNC", "SAS"]):
                                    if not any(k in cand.upper() for k in ["CEDENTE", "PRESTATORE", "CESSIONARIO", "COMMITTENTE"]):
                                        current_header['supplier'] = re.split(r'(?i)\s{2,}|P\.I\.|C\.F\.|TD\d+|VIA |CORSO |PIAZZA |VIALE ', cand)[0].strip()
                                        break

            # 2. ARTICOLI
            c_m = re.search(r'(?i)(ART\.CLI\.|AswArtFor|Codice Art\.|ART\.)\s*:?\s*(\S+)', line)
            v_m = re.search(r'(?i)Quantita:\s*([\d\.,]+).*?Valore unitario:\s*([\d\.,]+).*?Valore totale:\s*([\d\.,]+)', line)
            
            # Tabella ERP standard: [Qty] [Price] [Total] [IVA]
            t_r = re.search(r'([0-9\.,]{2,})\s+([0-9\.,]{2,})\s+([0-9\.,]{2,})\s+(\d{1,2}[\.,]\d{2})', line) if not v_m else None

            if c_m:
                k, v = c_m.groups()
                if "CLI" in k.upper(): current_item_data['customer_code'] = v
                else: current_item_data['code'] = v
                continue 

            if "Tipo:" in line and "Valore:" in line:
                tm = re.search(r'Tipo:\s*(.*?)\s*Valore:\s*(\S+)', line)
                if tm and "LINEA" not in tm.group(1).upper():
                    current_item_data['code'] = tm.group(2)
                continue

            if v_m or t_r:
                def p_n(s):
                    s = s.strip()
                    if ',' in s and '.' in s: return float(s.replace('.', '').replace(',', '.'))
                    return float(s.replace(',', '.'))
                
                qty, price, tot = v_m.groups() if v_m else (t_r.group(1), t_r.group(2), t_r.group(3))
                full_desc = " ".join(buffer_desc + ([line[:t_r.start()].strip()] if t_r else [])).strip()
                
                current_items.append(ParsedInvoiceItem(
                    code=str(current_item_data.get('code', '')),
                    customer_code=str(current_item_data.get('customer_code', '')),
                    description=clean_desc_text(full_desc) or "Senza descrizione",
                    quantity=p_n(qty),
                    unit_price=p_n(price),
                    total_price=p_n(tot)
                ))
                current_item_data = {}
                buffer_desc = []
            else:
                l_ign = ["FATTURA", "CEDENTE", "P.I.", "PAGE", "PRODOTTI", "DATI", "RIFERIMENTI", "SCONTI ALIQUOTA", "U.M. QUANTITÀ", "VIA ", "CORSO", "PIAZZA", "BARZANO", "VIGEVANO", "STRADA "]
                if line.strip() and not any(k in line_up for k in l_ign):
                    buffer_desc.append(line.strip())

        save_current_invoice()
        return invoices

    def parse_sacchi_layout(self, text: str, file_path: str) -> List[ParsedInvoice]:
        """Parser specifico per layout Sacchi (multi-fattura) con precisione migliorata."""
        lines = text.split('\n')
        invoices = []
        current_items = []
        curr_doc_number, curr_doc_date = None, None
        curr_supplier = "SACCHI GIUSEPPE S.P.A."
        val_regex = re.compile(r'\b([A-Z]{1,2})\s+([0-9\.,]{2,})\s+([0-9\.,]+)\s+([0-9\.,]+)')
        buffer_lines = []
        parsing_active = False

        def finalize_invoice():
            nonlocal current_items, curr_doc_number, curr_doc_date
            if current_items and curr_doc_number:
                invoices.append(ParsedInvoice(
                    supplier_name=curr_supplier,
                    date=curr_doc_date or datetime.now().date(),
                    number=curr_doc_number,
                    total_amount=sum(item.total_price for item in current_items),
                    items=list(current_items),
                    original_file_path=file_path
                ))
            current_items = []

        for i, line in enumerate(lines):
            line_up = line.upper()
            if "DOCUMENTO" in line_up:
                new_num, new_date = None, None
                for j in range(1, 10):
                    if i+j >= len(lines): break
                    sub = lines[i+j]
                    num_m = re.search(r'\b(\d{8,})\b', sub)
                    if num_m and num_m.group(1) != "00689730133": new_num = num_m.group(1)
                    date_m = re.search(r'(\d{2}/\d{2}/\d{4})', sub)
                    if date_m: 
                        try:
                            new_date = datetime.strptime(date_m.group(1), '%d/%m/%Y').date()
                        except: pass
                if new_num:
                    if new_num != curr_doc_number:
                        finalize_invoice()
                        curr_doc_number, curr_doc_date = new_num, new_date
                        parsing_active = False
                    buffer_lines = [] # Clear buffer on header/page repeat

            if "PRODOTTI E SERVIZI" in line_up: 
                parsing_active = True
                buffer_lines = [] # Reinforce buffer clear on start of items
                continue

            if not parsing_active: continue
            if any(k in line_up for k in ["TOTALE MERCE", "TOTALE DOCUMENTO", "SCONTI ALIQUOTA", "RIGA DESCRIZIONE", "U.M. QUANTITÀ"]): 
                buffer_lines = []
                continue

            match = val_regex.search(line)
            if match:
                def p_n(s):
                    if ',' in s and '.' in s: return float(s.replace('.', '').replace(',', '.'))
                    return float(s.replace(',', '.'))
                
                qty, price, tot = p_n(match.group(2)), p_n(match.group(3)), p_n(match.group(4))
                full_desc = " ".join(buffer_lines).strip()
                
                m_cust = re.search(r'ART\.CLI\.\s*([\w\d-]+)', full_desc)
                cust_code = m_cust.group(1) if m_cust else ""
                code = ""
                if not cust_code:
                    m_c = re.search(r'ART\.\s*([\w\d]+)', full_desc)
                    code = m_c.group(1) if m_c else ""
                
                clean_desc = re.sub(r'ART\.CLI\.\s*[\w\d-]+', '', full_desc)
                clean_desc = re.sub(r'ART\.\s*[\w\d]+', '', clean_desc)
                clean_desc = re.sub(r'^\d+\s+', '', clean_desc).strip()
                if line[:match.start()].strip(): clean_desc += " " + line[:match.start()].strip()
                
                # Metadata Cleaning
                clean_desc = re.sub(r'(?i)\d{4,}/\d{2,}\s+del\s+\d{2}[-/]\d{2}[-/]\d{2,4}', '', clean_desc)
                clean_desc = re.sub(r'(?i)AswTRiga\s*[:]\s*\w+\s*#\w+#', '', clean_desc)
                for s in ["Sconti Aliquota", "Natura Addebiti", "Addebiti Iva %", "DdT num.", "fornitore"]:
                    clean_desc = re.sub(f'(?i){re.escape(s)}', '', clean_desc)
                clean_desc = re.sub(r'(?i)\s+\b(PZ|PCE|M|ML|MT|LMT|KG|GR|SET)\b\s*$', '', clean_desc).strip()

                current_items.append(ParsedInvoiceItem(
                    code=code, customer_code=cust_code,
                    description=clean_desc or "Senza descrizione",
                    quantity=qty, unit_price=price, total_price=tot
                ))
                buffer_lines = []
            else:
                l_ign = ["DESCRIZIONE", "PREZZO", "QUANTITÀ", "CODICE", "UM", "CEDENTE", "P.I.", "CORSO", "VIA ", "BARZANO", "VIGEVANO", "STRADA ", "ADDEBITI", "IVA", "NATURA", "RIGA"]
                if line.strip() and not any(k in line_up for k in l_ign):
                    buffer_lines.append(line.strip())

        finalize_invoice()
        return invoices

    def parse(self, file_path: str) -> List[ParsedInvoice]:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
            
            # Se troviamo i marcatori di una fattura (SdI o Generica), usiamo il parser robusto
            # Cerchiamo Denominazione, Numero o Data che sono comuni a quasi tutti i layout
            if any(k in text for k in ["Numero", "Data", "Denominazione", "FATTURA ELETTRONICA"]):
                try:
                    res = self.parse_sdi_layout(text, file_path)
                    if res: return res
                except: pass
            
            # Fallback Sacchi
            if "SACCHI GIUSEPPE S.P.A." in text:
                try:
                    res = self.parse_sacchi_layout(text, file_path)
                    if res: return res
                except: pass
            
            return []
