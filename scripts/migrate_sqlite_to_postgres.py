import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Aggiungi cartella root al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import (
    Supplier as TargetSupplier,
    Invoice as TargetInvoice,
    InvoiceItem as TargetInvoiceItem,
    Product as TargetProduct,
    SupplierProduct as TargetSupplierProduct,
    init_db,
    get_db_session
)

def migrate_invoices(source_sqlite_path=r"\\Angeleri_new\Pubblica\Database\Fornitori\invoices.db", target_db_url=None):
    print(f"\n==========================================")
    print(f"MIGRAZIONE FATTURE FORNITORI DA SQLITE")
    print(f"Sorgente: {source_sqlite_path}")
    print(f"Destinazione: {target_db_url or 'Default DB'}")
    print(f"==========================================\n")

    if not os.path.exists(source_sqlite_path):
        # Fallback locale se percorso di rete non risponde
        local_fallback = "invoices.db"
        if os.path.exists(local_fallback):
            print(f"Percorso di rete non trovato, utilizzo fallback locale: {local_fallback}")
            source_sqlite_path = local_fallback
        else:
            print(f"ERRORE: Impossibile trovare il database sorgente {source_sqlite_path}")
            return

    # Inizializza target
    if target_db_url:
        init_db(target_db_url)
    target_session = get_db_session()

    # Connessione a sorgente SQLite
    source_engine = create_engine(f"sqlite:///{os.path.abspath(source_sqlite_path).replace('\\', '/')}")
    SourceSession = sessionmaker(bind=source_engine)
    source_session = SourceSession()

    try:
        from sqlalchemy import text
        # 1. Migrazione Fornitori
        suppliers_rows = source_session.execute(text("SELECT id, name, piva FROM suppliers")).fetchall()
        print(f"Trovati {len(suppliers_rows)} fornitori da migrare...")
        supplier_id_map = {} # old_id -> new_id
        
        for row in suppliers_rows:
            old_id, name, piva = row
            name_clean = name.strip()
            
            existing = target_session.query(TargetSupplier).filter_by(name=name_clean).first()
            if not existing:
                existing = TargetSupplier(name=name_clean, piva=piva)
                target_session.add(existing)
                target_session.flush()
            supplier_id_map[old_id] = existing.id

        target_session.commit()
        print("Fornitori sincronizzati con successo.")

        # 2. Migrazione Fatture & Righe
        invoices_rows = source_session.execute(text("SELECT id, supplier_id, date, number, total_amount, file_path FROM invoices")).fetchall()
        print(f"Trovate {len(invoices_rows)} fatture acquisto da migrare...")

        inv_count = 0
        items_count = 0

        for inv_row in invoices_rows:
            old_inv_id, old_supp_id, inv_date_str, number, total_amount, file_path = inv_row
            new_supp_id = supplier_id_map.get(old_supp_id)
            if not new_supp_id:
                continue

            # Parsing data se stringa
            from datetime import datetime
            if isinstance(inv_date_str, str):
                try:
                    inv_date = datetime.strptime(inv_date_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
            else:
                inv_date = inv_date_str

            # Verifica esistenza fattura (evita duplicati)
            existing_inv = target_session.query(TargetInvoice).filter_by(
                supplier_id=new_supp_id,
                date=inv_date,
                number=str(number)
            ).first()

            if not existing_inv:
                existing_inv = TargetInvoice(
                    supplier_id=new_supp_id,
                    date=inv_date,
                    number=str(number),
                    total_amount=total_amount or 0.0,
                    file_path=file_path
                )
                target_session.add(existing_inv)
                target_session.flush()
                inv_count += 1

            # Leggi righe della fattura sorgente
            item_rows = source_session.execute(
                text("SELECT code, customer_code, description, quantity, unit_price, total_price FROM invoice_items WHERE invoice_id = :iid"),
                {"iid": old_inv_id}
            ).fetchall()

            for it in item_rows:
                code, cust_code, desc, qty, u_price, tot_price = it
                
                # Cerca eventuale matching con articolo master
                matched_prod_id = None
                if code:
                    # Cerca per codice alternativo fornitore
                    sp = target_session.query(TargetSupplierProduct).filter_by(
                        supplier_id=new_supp_id,
                        supplier_code=code.strip()
                    ).first()
                    if sp:
                        matched_prod_id = sp.product_id
                    else:
                        # Cerca direttamente per codice master
                        prod = target_session.query(TargetProduct).filter_by(code=code.strip()).first()
                        if prod:
                            matched_prod_id = prod.id

                item = TargetInvoiceItem(
                    invoice_id=existing_inv.id,
                    product_id=matched_prod_id,
                    code=code,
                    customer_code=cust_code,
                    description=desc or "",
                    quantity=qty or 0.0,
                    unit_price=u_price or 0.0,
                    total_price=tot_price or 0.0
                )
                target_session.add(item)
                items_count += 1

            if inv_count % 100 == 0:
                target_session.flush()

        target_session.commit()
        print(f"\nMigrazione completata con successo!")
        print(f"• Fatture importate: {inv_count}")
        print(f"• Righe articolo importate: {items_count}")

    finally:
        source_session.close()
        target_session.close()

if __name__ == "__main__":
    migrate_invoices()
