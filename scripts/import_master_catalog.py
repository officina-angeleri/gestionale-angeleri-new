import os
import sys
import re
import pdfplumber

# Aggiungi cartella root al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_db_session, Product, ProductLegacyCode, SupplierProduct, Supplier

def determine_type_and_category(code: str):
    """Determina tipo e categoria dell'articolo a partire dal prefisso del codice."""
    code = code.strip().upper()
    if code.startswith('L010'):
        return 'LAVORAZIONE', 'Alluminio'
    elif code.startswith('L011'):
        return 'LAVORAZIONE', 'Ferro'
    elif code.startswith('L012'):
        return 'LAVORAZIONE', 'Bronzo/Speciali'
    elif code.startswith('L040'):
        return 'LAVORAZIONE', 'Carpenteria'
    elif code.startswith('L050'):
        return 'LAVORAZIONE', 'Semilavorati/Basamenti'
    elif code.startswith('L'):
        return 'LAVORAZIONE', 'Generale'
    elif code.startswith('A010'):
        return 'ACQUISTO', 'Fusioni'
    elif code.startswith('A050'):
        return 'ACQUISTO', 'Alluminio Grezzo'
    elif code.startswith('A500'):
        return 'ACQUISTO', 'Boccole'
    elif code.startswith('A550'):
        return 'ACQUISTO', 'Pulegge'
    elif code.startswith('A560'):
        return 'ACQUISTO', 'Cinghie/Catene'
    elif code.startswith('A570'):
        return 'ACQUISTO', 'Molle'
    elif code.startswith('A580'):
        return 'ACQUISTO', 'Guarnizioni/OR'
    elif code.startswith('A800'):
        return 'ACQUISTO', 'Elettrico/Elettronico'
    elif code.startswith('A850'):
        return 'ACQUISTO', 'Pistole/Verniciatura'
    elif code.startswith('A950'):
        return 'ACQUISTO', 'Utensileria'
    elif code.startswith('A960'):
        return 'ACQUISTO', 'Viteria/Bulloneria'
    elif code.startswith('A'):
        return 'ACQUISTO', 'Commerciale'
    elif code.startswith('SP-'):
        return 'RICAMBIO', 'Ricambi Speciali'
    elif code.startswith('M2-') or code.startswith('M3-'):
        return 'GRUPPO', 'Gruppi Premontati'
    return 'ALTRO', 'Varie'

def parse_float(val_str):
    if not val_str:
        return 0.0
    val_str = val_str.replace('.', '').replace(',', '.').strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def import_lista_articoli(session, pdf_path):
    print(f"\n[1/4] Importazione Anagrafica Base da: {pdf_path}...")
    if not os.path.exists(pdf_path):
        print(f"File non trovato: {pdf_path}")
        return 0

    count = 0
    # Pattern: Codice all'inizio, poi testo, poi numero costo alla fine
    # es: A010-0001 FUSIONE CORPO MACCHINA ICT 60 MINI peso unitario kg 3,11 38
    code_pattern = re.compile(r'^([A-Z0-9]{1,4}-[0-9]{3,5})\s+(.*?)(?:\s+([\d.,]+))?$')

    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip()
                if not line or line.startswith('Codice Descrizione'):
                    continue
                
                m = code_pattern.match(line)
                if m:
                    code, desc, cost_str = m.groups()
                    cost = parse_float(cost_str) if cost_str else 0.0
                    
                    prod_type, category = determine_type_and_category(code)
                    
                    product = session.query(Product).filter_by(code=code).first()
                    if not product:
                        product = Product(
                            code=code,
                            name=desc.strip(),
                            type=prod_type,
                            category=category,
                            production_cost=cost
                        )
                        session.add(product)
                        count += 1
                    else:
                        if cost > 0 and product.production_cost == 0.0:
                            product.production_cost = cost
            if (p_idx + 1) % 25 == 0 or (p_idx + 1) == len(pdf.pages):
                session.flush()
                print(f"  Elaborate {p_idx+1}/{len(pdf.pages)} pagine... ({count} articoli inseriti)")
    
    session.commit()
    print(f"Totale articoli base inseriti: {count}")
    return count

def import_comparativo_codici(session, pdf_path):
    print(f"\n[2/4] Importazione Comparativo Vecchio -> Nuovo da: {pdf_path}...")
    if not os.path.exists(pdf_path):
        print(f"File non trovato: {pdf_path}")
        return 0

    count = 0
    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip().replace('\u200b', '')
                if not line or line.startswith('Articolo (interno)'):
                    continue
                
                m = re.match(r'^([A-Z0-9]{1,4}-[0-9]{3,5})\s*-\s*(.+)$', line)
                if not m:
                    continue

                master_code = m.group(1).strip()
                rest = m.group(2).strip()

                if re.search(r'\s+\.\s+', rest):
                    continue

                leg_code = None
                leg_desc = None
                cost = 0.0
                list_price = 0.0

                # Formato A: codice legacy ripetuto (es. ' 3150-10 3150-10 ')
                m_rep = re.search(r'\s+([0-9A-Za-z_/-]{2,25})\s+\1\s+(.+)$', rest)
                if m_rep:
                    leg_code = m_rep.group(1).strip().upper()
                    after = m_rep.group(2).strip()
                    m_prices = re.search(r'([\d.,]+)\s+([\d.,]+)$', after)
                    if m_prices:
                        leg_desc = after[:m_prices.start()].strip()
                        cost = parse_float(m_prices.group(1))
                        list_price = parse_float(m_prices.group(2))
                    else:
                        m_single_price = re.search(r'([\d.,]+)$', after)
                        if m_single_price:
                            leg_desc = after[:m_single_price.start()].strip()
                            cost = parse_float(m_single_price.group(1))
                        else:
                            leg_desc = after
                else:
                    # Formato B: codice legacy specifico singolo (es. RI..., T-..., X-..., R-...)
                    m_sing = re.search(r'\s+([A-Z]{1,2}-[0-9A-Za-z_/-]{2,20}|RI[0-9]{3,5}[A-Z\.]*|TH[0-9A-Z_-]+|X-[0-9A-Za-z_/-]+|T-[0-9A-Za-z_/-]+)\s+(.+)$', rest)
                    if m_sing:
                        leg_code = m_sing.group(1).strip().upper()
                        after = m_sing.group(2).strip()
                        m_prices = re.search(r'([\d.,]+)\s+([\d.,]+)$', after)
                        if m_prices:
                            leg_desc = after[:m_prices.start()].strip()
                            cost = parse_float(m_prices.group(1))
                            list_price = parse_float(m_prices.group(2))
                        else:
                            m_single_price = re.search(r'([\d.,]+)$', after)
                            if m_single_price:
                                leg_desc = after[:m_single_price.start()].strip()
                                cost = parse_float(m_single_price.group(1))
                            else:
                                leg_desc = after

                if not leg_code:
                    continue

                # Trova o crea l'articolo master
                product = session.query(Product).filter_by(code=master_code).first()
                if not product:
                    p_type, p_cat = determine_type_and_category(master_code)
                    product = Product(
                        code=master_code,
                        name=leg_desc or master_code,
                        type=p_type,
                        category=p_cat,
                        production_cost=cost,
                        list_price=list_price
                    )
                    session.add(product)
                    session.flush()
                else:
                    if list_price > 0 and product.list_price == 0.0:
                        product.list_price = list_price
                    if cost > 0 and product.production_cost == 0.0:
                        product.production_cost = cost

                # Aggiungi il codice legacy se non presente
                legacy = session.query(ProductLegacyCode).filter_by(
                    product_id=product.id,
                    legacy_code=leg_code
                ).first()
                if not legacy:
                    legacy = ProductLegacyCode(
                        product_id=product.id,
                        legacy_code=leg_code,
                        legacy_description=leg_desc or "Da comparativo codici",
                        cost_std=cost,
                        list_price=list_price
                    )
                    session.add(legacy)
                    count += 1
            session.flush()
    
    session.commit()
    print(f"Totale codici legacy/esploso mappati: {count}")
    return count

def import_articoli_fornitori(session, pdf_path):
    print(f"\n[3/4] Importazione Equivalenze Fornitori da: {pdf_path}...")
    if not os.path.exists(pdf_path):
        print(f"File non trovato: {pdf_path}")
        return 0

    count = 0
    # Esempio linee:
    # ANEST IWATA ITALIA SRL 03810620 A850-0050 GUARNIZ.ASTINA
    # ASPES SPA CMPT516 A560-0045 CINGHIA DENTATA 16 T5 A METRAGGIO
    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip()
                if not line or line.startswith('Elenco Articoli') or line.startswith('Fornitore Articolo'):
                    continue
                
                # Cerca il codice interno Angeleri nella riga (es. A850-0050, L012-0023)
                m = re.search(r'\b([A-Z0-9]{1,4}-[0-9]{3,5})\b', line)
                if m:
                    master_code = m.group(1)
                    idx = m.start()
                    before = line[:idx].strip()
                    after = line[m.end():].strip()
                    
                    # Prima del master code c'è: Fornitore + Codice Fornitore
                    parts = before.split()
                    if len(parts) >= 2:
                        supp_code = parts[-1].strip('\u200b') # Rimuove zero-width space
                        supp_name = " ".join(parts[:-1]).strip('\u200b* ')
                    elif len(parts) == 1:
                        supp_code = parts[0].strip('\u200b')
                        supp_name = "Fornitore Generale"
                    else:
                        continue

                    # Trova o crea articolo master
                    product = session.query(Product).filter_by(code=master_code).first()
                    if not product:
                        p_type, p_cat = determine_type_and_category(master_code)
                        product = Product(
                            code=master_code,
                            name=after if after else master_code,
                            type=p_type,
                            category=p_cat
                        )
                        session.add(product)
                        session.flush()

                    # Trova o crea il fornitore
                    supplier = None
                    if supp_name:
                        supplier = session.query(Supplier).filter_by(name=supp_name).first()
                        if not supplier:
                            supplier = Supplier(name=supp_name)
                            session.add(supplier)
                            session.flush()

                    # Crea associazione
                    supp_prod = session.query(SupplierProduct).filter_by(
                        product_id=product.id,
                        supplier_code=supp_code
                    ).first()
                    if not supp_prod:
                        supp_prod = SupplierProduct(
                            product_id=product.id,
                            supplier_id=supplier.id if supplier else None,
                            supplier_name=supp_name,
                            supplier_code=supp_code,
                            supplier_description=after
                        )
                        session.add(supp_prod)
                        count += 1
            session.flush()
    
    session.commit()
    print(f"Totale equivalenze fornitore collegate: {count}")
    return count

def import_listino_vendita(session, pdf_path):
    print(f"\n[4/4] Importazione Listino Prezzi Vendita da: {pdf_path}...")
    if not os.path.exists(pdf_path):
        print(f"File non trovato: {pdf_path}")
        return 0

    count = 0
    # Esempi:
    # 3150-12 3150-12 CARTER COPRI INGRANAGGI NR 38
    # A550-0038 PULEGGIA DENTATA 19 L050 X BUSSOLA 7
    line_pattern = re.compile(r'^([0-9A-Z_/-]{3,30})\s+(.*?)(?:\s+(NR|PZ|MT|KG))?\s+([\d.,]+)$')

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip()
                if not line or line.startswith('COD-ART'):
                    continue
                m = line_pattern.match(line)
                if m:
                    code, desc, um, price_str = m.groups()
                    price = parse_float(price_str)
                    if price > 0:
                        # 1. Prova a cercare come codice master (es. A550-0038)
                        product = session.query(Product).filter_by(code=code).first()
                        if product:
                            product.list_price = price
                            if um: product.unit_measure = um
                            count += 1
                        else:
                            # 2. Prova a cercare nei codici legacy (es. 3150-12)
                            legacy = session.query(ProductLegacyCode).filter_by(legacy_code=code).first()
                            if legacy and legacy.product:
                                legacy.list_price = price
                                if legacy.product.list_price == 0.0:
                                    legacy.product.list_price = price
                                count += 1

    session.commit()
    print(f"Totale prezzi di listino aggiornati: {count}")
    return count

def run_all(db_url=None):
    from app.database import init_db
    if db_url:
        init_db(db_url)
    session = get_db_session()
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'File_per_progetto'))
    
    import_lista_articoli(session, os.path.join(base_dir, 'Lista_articoli.pdf'))
    import_comparativo_codici(session, os.path.join(base_dir, 'comparativo_codici.pdf'))
    import_articoli_fornitori(session, os.path.join(base_dir, 'Articoli_fornitori.pdf'))
    import_listino_vendita(session, os.path.join(base_dir, 'Listino_vendita_pezzi.pdf'))
    
    total_prods = session.query(Product).count()
    total_leg = session.query(ProductLegacyCode).count()
    total_supp = session.query(SupplierProduct).count()
    print(f"\n==========================================")
    print(f"RIEPILOGO CATALOGO MASTER:")
    print(f"• Totale Articoli Master: {total_prods}")
    print(f"• Mappature Codici Vecchi/Esplosi: {total_leg}")
    print(f"• Codici Alternativi Fornitore: {total_supp}")
    print(f"==========================================\n")

if __name__ == "__main__":
    run_all()
