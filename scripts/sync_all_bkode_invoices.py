"""
Script per l'importazione massiva di TUTTE le fatture fornitori (fatforxmlList) 
e fatture clienti (fatcliList) presenti su B-Kode Cloud nel database PostgreSQL.
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, '.')

from app.database import get_db_session, Invoice, SalesInvoice, Supplier, Customer
from app.utils.bkode_client import BKodeClient

def main():
    print("=" * 70)
    print("  SINCRONIZZAZIONE MASSIVA FATTURE B-KODE -> POSTGRESQL")
    print("=" * 70)

    client = BKodeClient()
    if not client.ensure_authenticated():
        print("[ERRORE] Impossibile autenticarsi con il cookie salvato.")
        return

    session = get_db_session()

    # ==============================================================
    # 1. FATTURE FORNITORI (fatforxmlList - 7.122 fatture)
    # ==============================================================
    print("\n--> 1. Estrazione Fatture Fornitori Elettroniche (fatforxmlList)...")
    
    # Precarica fornitori esistenti per velocità massima
    suppliers_cache = {s.name.strip().upper(): s for s in session.query(Supplier).all()}
    
    # Precarica chiavi fatture esistenti: (supplier_id, number, date)
    existing_invoices = set(
        session.query(Invoice.supplier_id, Invoice.number, Invoice.date).all()
    )
    print(f"  Fatture fornitori già presenti a DB: {len(existing_invoices)}")

    start = 0
    limit = 500
    new_invoices_count = 0
    total_fetched = 0

    while True:
        res = client._post_grid('fatforxmlList', {'start': str(start), 'limit': str(limit)})
        if not res or not res.get('items'):
            break

        items = res['items']
        total_fetched += len(items)
        batch_new = 0

        for pinv in items:
            num = str(pinv.get("fxml_nr_fat") or pinv.get("xml_num_doc") or pinv.get("doc_num") or "").strip()
            dt_str = pinv.get("fxml_dt_fat") or pinv.get("xml_dt_doc") or pinv.get("doc_dt") or ""
            if not num or not dt_str:
                continue

            try:
                dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
            except Exception:
                continue

            supp_raw = (pinv.get("fxml_ragsoc_1") or pinv.get("for_ragsoc_1") or pinv.get("xml_ced_ragsoc") or "").strip()
            if not supp_raw:
                continue

            from app.controllers.invoice_manager import InvoiceManager
            supp_name = InvoiceManager._normalize_supplier(supp_raw)
            supp_key = supp_name.upper()
            supp = suppliers_cache.get(supp_key)
            if not supp:
                # Cerca case-insensitive nel DB o crea
                supp = session.query(Supplier).filter(Supplier.name.ilike(supp_name)).first()
                if not supp:
                    supp = Supplier(name=supp_name)
                    session.add(supp)
                    session.flush()
                suppliers_cache[supp_key] = supp

            inv_key = (supp.id, num, dt)
            if inv_key not in existing_invoices:
                tot = float(pinv.get("fxml_tot") or pinv.get("fxml_imp") or pinv.get("xml_tot_doc") or 0.0)
                file_name = pinv.get("fxml_file") or pinv.get("fxml_file_sdi") or ""
                new_inv = Invoice(
                    supplier_id=supp.id,
                    number=num,
                    date=dt,
                    total_amount=tot,
                    file_path=file_name
                )
                session.add(new_inv)
                existing_invoices.add(inv_key)
                new_invoices_count += 1
                batch_new += 1

        session.commit()
        print(f"  Elaborate {total_fetched} / {res.get('totalCount', '?')} fatture fornitore (Nuove inserite: {batch_new})...")

        if len(items) < limit:
            break
        start += limit

    print(f"  [OK] Completate fatture fornitori: {new_invoices_count} nuove fatture salvate su PostgreSQL.")

    # ==============================================================
    # 2. FATTURE CLIENTI (fatcliList - 12.073 fatture)
    # ==============================================================
    print("\n--> 2. Estrazione Fatture Clienti di Vendita (fatcliList)...")
    customers_cache = {c.name.strip().upper(): c for c in session.query(Customer).all()}
    existing_sales = set(
        session.query(SalesInvoice.customer_id, SalesInvoice.number, SalesInvoice.year).all()
    )
    print(f"  Fatture clienti già presenti a DB: {len(existing_sales)}")

    start = 0
    limit = 500
    new_sales_count = 0
    total_sales_fetched = 0

    while True:
        res = client._post_grid('fatcliList', {'start': str(start), 'limit': str(limit)})
        if not res or not res.get('items'):
            break

        items = res['items']
        total_sales_fetched += len(items)
        batch_new_s = 0

        for inv in items:
            num = str(inv.get("fat_nr") or inv.get("fat_num") or inv.get("doc_num") or "").strip()
            dt_str = inv.get("fat_dt") or inv.get("doc_dt") or ""
            if not num or not dt_str:
                continue

            try:
                dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
            except Exception:
                continue

            cust_name = (inv.get("cli_ragsoc_1") or "Cliente Sconosciuto").strip()
            cust_key = cust_name.upper()
            cust = customers_cache.get(cust_key)
            if not cust:
                cust = session.query(Customer).filter(Customer.name.ilike(cust_name)).first()
                if not cust:
                    cust = Customer(name=cust_name)
                    session.add(cust)
                    session.flush()
                customers_cache[cust_key] = cust

            s_key = (cust.id, num, dt.year)
            if s_key not in existing_sales:
                tot = float(inv.get("fat_imp_net") or inv.get("fat_tot_doc") or inv.get("doc_tot") or 0.0)
                doc_type = inv.get("cau_des") or inv.get("fat_tipo") or "FATTURA"
                new_s = SalesInvoice(
                    customer_id=cust.id,
                    number=num,
                    date=dt,
                    year=dt.year,
                    doc_type=doc_type,
                    total_amount=tot
                )
                session.add(new_s)
                existing_sales.add(s_key)
                new_sales_count += 1
                batch_new_s += 1

        session.commit()
        print(f"  Elaborate {total_sales_fetched} / {res.get('totalCount', '?')} fatture clienti (Nuove inserite: {batch_new_s})...")

        if len(items) < limit:
            break
        start += limit

    print(f"  [OK] Completate fatture clienti: {new_sales_count} nuove fatture salvate su PostgreSQL.")

    print("\n" + "=" * 70)
    print("  SINCRONIZZAZIONE TOTALE COMPLETATA CON SUCCESSO!")
    print(f"  Fatture Fornitori totali nel DB: {session.query(Invoice).count()}")
    print(f"  Fatture Clienti totali nel DB:   {session.query(SalesInvoice).count()}")
    print("=" * 70)

if __name__ == '__main__':
    main()
