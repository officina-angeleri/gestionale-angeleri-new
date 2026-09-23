import os
import sys
import re
import pdfplumber

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_db, get_db_session, Product, ProductLegacyCode

DEFAULT_PG_URL = "postgresql+psycopg2://angeleri:AngeleriPassword2026!@192.168.1.38:5433/angeleri_db"

def parse_float(val):
    if not val: return 0.0
    val = val.strip().replace('€', '').replace(' ', '').replace('.', '').replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def rebuild():
    db_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PG_URL
    init_db(db_url)
    session = get_db_session()

    print("=== PULIZIA CODICI LEGACY SINTETICI ===")
    deleted = session.query(ProductLegacyCode).filter(ProductLegacyCode.legacy_description.like('Esploso%')).delete(synchronize_session=False)
    session.commit()
    print(f"Eliminati {deleted} codici legacy sintetici generati dai pallini degli esplosi.")

    # Mappa articoli per codice master
    products = {p.code.upper().strip(): p for p in session.query(Product).all()}

    pdf_path = "File_per_progetto/comparativo_codici.pdf"
    print(f"\n=== IMPORTAZIONE UFFICIALE DA {pdf_path} ===")
    
    imported = 0
    updated = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            for line in text.split('\n'):
                line = line.strip().replace('\u200b', '')
                if not line or line.startswith('Articolo (interno)'):
                    continue

                m = re.match(r'^([A-Z0-9]{1,4}-[0-9]{3,5})\s*-\s*(.+)$', line)
                if not m:
                    continue

                master_code = m.group(1).strip()
                rest = m.group(2).strip()

                # Ignora righe con solo un punto '.' (nessun codice legacy)
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
                    # Estrai prezzi in fondo
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

                prod = products.get(master_code.upper())
                if not prod:
                    continue

                # Aggiorna prezzi se presenti
                if list_price > 0 and prod.list_price == 0.0:
                    prod.list_price = list_price
                if cost > 0 and prod.production_cost == 0.0:
                    prod.production_cost = cost

                # Verifica se già presente
                existing = session.query(ProductLegacyCode).filter_by(
                    product_id=prod.id,
                    legacy_code=leg_code
                ).first()

                if not existing:
                    new_rec = ProductLegacyCode(
                        product_id=prod.id,
                        legacy_code=leg_code,
                        legacy_description=leg_desc or f"Da comparativo codici",
                        cost_std=cost,
                        list_price=list_price
                    )
                    session.add(new_rec)
                    imported += 1
                else:
                    if leg_desc and (not existing.legacy_description or existing.legacy_description == 'Da comparativo codici'):
                        existing.legacy_description = leg_desc
                    if cost > 0 and existing.cost_std == 0.0:
                        existing.cost_std = cost
                    if list_price > 0 and existing.list_price == 0.0:
                        existing.list_price = list_price
                    updated += 1

    session.commit()
    print(f"Completato! Nuovi inseriti: {imported}, Aggiornati: {updated}")

    total_official = session.query(ProductLegacyCode).count()
    print(f"Totale codici legacy ufficiali nel DB: {total_official}")

    session.close()

if __name__ == '__main__':
    rebuild()
