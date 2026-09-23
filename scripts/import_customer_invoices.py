import os
import sys
import re
import glob
from datetime import datetime
import pdfplumber

# Aggiungi cartella root al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import (
    Customer,
    SalesInvoice,
    SalesInvoiceItem,
    Product,
    ProductLegacyCode,
    init_db,
    get_db_session
)

def parse_float(val_str):
    if not val_str:
        return 0.0
    s = str(val_str).replace('%', '').strip()
    if '.' in s and ',' in s:
        if s.rfind(',') > s.rfind('.'):
            # Formato italiano: 1.234,56
            s = s.replace('.', '').replace(',', '.')
        else:
            # Formato inglese: 1,234.56
            s = s.replace(',', '')
    elif ',' in s:
        # Solo virgola: 79,0000 -> 79.0
        s = s.replace(',', '.')
    elif '.' in s:
        # Solo punto: es. 10.0000 o 1.0000 (XML / SdI export in PDF)
        if s.count('.') > 1:
            s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return 0.0

TD_PATTERN = re.compile(r'^(TD\d{2}(?:\s*-\s*(?:Fattura\s+differita|Fattura\s+ordinaria|Fattura|Nota\s+di\s+credito|Nota\s+di\s+debito))?)\s*(.*)', re.IGNORECASE)
VAL_PATTERN = re.compile(r'(.*?)\s+(NR|KG|PZ|MT|H|KG\.|ORE|LT)\s+([\d.,]+)\s+([\d.,]+)(?:\s+([\d.,]+%))?\s+([\d.,-]+)')

def import_single_pdf(session, pdf_path):
    filename = os.path.basename(pdf_path)
    print(f"\n---> Inizio elaborazione: {filename}...")
    
    invoices_imported = 0
    items_imported = 0
    pages_skipped = 0

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"  Pagine totali nel documento: {total_pages}")

        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or 'Off. Mecc. ANGELERI s.r.l.' not in text:
                pages_skipped += 1
                continue

            lines = text.split('\n')

            # 1. Estrazione Testata Documento
            doc_type = "TD01"
            client_name = "Cliente Sconosciuto"
            inv_num = ""
            inv_date = None
            inv_total = 0.0
            client_piva = ""

            for idx, l in enumerate(lines[:10]):
                if 'Off. Mecc. ANGELERI s.r.l.' in l:
                    rest = l.replace('Off. Mecc. ANGELERI s.r.l.', '').strip()
                    m_td = TD_PATTERN.match(rest)
                    if m_td:
                        doc_type = m_td.group(1).strip()
                        client_name = m_td.group(2).strip() or "Cliente Sconosciuto"
                    else:
                        client_name = rest or "Cliente Sconosciuto"

                    if idx + 1 < len(lines):
                        next_l = lines[idx+1]
                        m_num = re.search(r'via Ruffini,\s*15/3\s+([0-9A-Z/_-]+)\s+(.*)', next_l)
                        if m_num:
                            inv_num = m_num.group(1).strip()

                    if idx + 2 < len(lines):
                        date_l = lines[idx+2]
                        m_date = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', date_l)
                        if m_date:
                            try:
                                inv_date = datetime.strptime(m_date.group(1), "%d/%m/%Y").date()
                            except ValueError:
                                pass

                    if idx + 3 < len(lines):
                        tot_l = lines[idx+3]
                        m_eur = re.search(r'EUR\s+([\d.,]+)', tot_l)
                        if m_eur:
                            inv_total = parse_float(m_eur.group(1))
                        m_piva = re.search(r'(?:P\.I\.|C\.F\.)\s+([A-Z0-9]+)$', tot_l)
                        if m_piva:
                            client_piva = m_piva.group(1).strip()

            if not inv_num or not inv_date:
                pages_skipped += 1
                continue

            inv_year = inv_date.year

            # 2. Cliente (Anagrafica)
            customer = None
            if client_piva:
                customer = session.query(Customer).filter_by(piva_cf=client_piva).first()
            if not customer and client_name:
                customer = session.query(Customer).filter_by(name=client_name).first()

            if not customer:
                customer = Customer(
                    name=client_name,
                    piva_cf=client_piva or None
                )
                session.add(customer)
                session.flush()
            else:
                if client_piva and not customer.piva_cf:
                    customer.piva_cf = client_piva

            # 3. Fattura Vendita (Idempotente)
            invoice = session.query(SalesInvoice).filter_by(
                customer_id=customer.id,
                year=inv_year,
                number=inv_num
            ).first()

            if not invoice:
                invoice = SalesInvoice(
                    customer_id=customer.id,
                    number=inv_num,
                    date=inv_date,
                    year=inv_year,
                    doc_type=doc_type,
                    total_amount=inv_total,
                    file_path=filename
                )
                session.add(invoice)
                session.flush()
                invoices_imported += 1
            else:
                # Fattura già presente, salta per evitare duplicati
                continue

            # 4. Righe Articoli
            in_items = False
            current_line_num = None
            current_raw_code = None

            for l in lines:
                if 'PRODOTTI E SERVIZI' in l:
                    in_items = True
                    continue
                if 'RIFERIMENTI D.D.T.' in l or 'RIEPILOGO DOCUMENTO' in l:
                    in_items = False
                    continue

                if in_items:
                    l_str = l.strip()
                    m_start = re.match(r'^(\d+)\s+(.*)', l_str)
                    if m_start:
                        r_num_str = m_start.group(1)
                        rest = m_start.group(2)
                        if rest.startswith('- D.D.T.') or rest.startswith('- A SALDO') or rest.startswith('- ORDINE'):
                            continue
                        if rest.startswith('INT '):
                            current_line_num = int(r_num_str)
                            current_raw_code = rest.replace('INT ', '').strip()
                            continue
                        else:
                            current_line_num = int(r_num_str)
                            current_raw_code = None
                            l_str = rest

                    # Controllo valori
                    m_val = VAL_PATTERN.search(l_str)
                    if m_val:
                        desc, um, qty_str, price_str, disc_str, tot_str = m_val.groups()
                        qty = parse_float(qty_str)
                        u_price = parse_float(price_str)
                        discount = parse_float(disc_str)
                        tot_price = parse_float(tot_str)

                        # Risoluzione Codice Articolo Master
                        matched_prod_id = None
                        if current_raw_code:
                            p = session.query(Product).filter_by(code=current_raw_code).first()
                            if p:
                                matched_prod_id = p.id
                            else:
                                leg = session.query(ProductLegacyCode).filter_by(legacy_code=current_raw_code).first()
                                if leg:
                                    matched_prod_id = leg.product_id

                        item = SalesInvoiceItem(
                            invoice_id=invoice.id,
                            product_id=matched_prod_id,
                            line_number=current_line_num,
                            raw_code=current_raw_code,
                            description=desc.strip(),
                            unit_measure=um,
                            quantity=qty,
                            unit_price=u_price,
                            discount=discount,
                            total_price=tot_price
                        )
                        session.add(item)
                        items_imported += 1

                        current_line_num = None
                        current_raw_code = None

            if (p_idx + 1) % 50 == 0:
                session.flush()
                print(f"    Pagina {p_idx+1}/{total_pages}... (Fatture: {invoices_imported}, Righe: {items_imported})")

    session.commit()
    print(f"  Completato {filename}: +{invoices_imported} fatture, +{items_imported} righe.")
    return invoices_imported, items_imported

def import_all_customer_invoices(db_url=None):
    if db_url:
        init_db(db_url)
    session = get_db_session()

    folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'File_per_progetto', 'Fatture_Clienti'))
    pdf_files = sorted(glob.glob(os.path.join(folder, "*.pdf")))

    print(f"\n==========================================")
    print(f"IMPORTAZIONE FATTURE CLIENTI (2019-2026)")
    print(f"Cartella: {folder}")
    print(f"File PDF trovati: {len(pdf_files)}")
    print(f"==========================================\n")

    tot_inv = 0
    tot_it = 0

    for pdf_path in pdf_files:
        invs, items = import_single_pdf(session, pdf_path)
        tot_inv += invs
        tot_it += items

    total_customers = session.query(Customer).count()
    total_invoices = session.query(SalesInvoice).count()
    total_items = session.query(SalesInvoiceItem).count()

    print(f"\n==========================================")
    print(f"RIEPILOGO VENDITE CLIENTI:")
    print(f"• Totale Clienti in Anagrafica: {total_customers}")
    print(f"• Totale Fatture Vendita: {total_invoices}")
    print(f"• Totale Righe Articoli Venduti: {total_items}")
    print(f"==========================================\n")

if __name__ == "__main__":
    import_all_customer_invoices()
