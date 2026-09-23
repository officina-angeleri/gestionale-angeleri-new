import os
import sys
import time

# Aggiungi cartella root al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_db, get_db_session, Product, ProductLegacyCode, SupplierProduct, Supplier, Invoice, InvoiceItem, Customer, SalesInvoice, SalesInvoiceItem
from scripts.import_master_catalog import run_all as run_catalog
from scripts.migrate_sqlite_to_postgres import migrate_invoices
from scripts.import_customer_invoices import import_all_customer_invoices

DEFAULT_PG_URL = "postgresql+psycopg2://angeleri:AngeleriPassword2026!@192.168.1.38:5433/angeleri_db"

def main():
    db_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PG_URL
    print(f"\n=======================================================")
    print(f"   GESTIONALE ANGELERI - PIPELINE MIGRAZIONE UNIFICATA")
    print(f"=======================================================")
    print(f"Target DB: {db_url}")
    
    start_time = time.time()
    
    print("\n---> [FASE 1/4] Inizializzazione Schema Database...")
    init_db(db_url)
    print("Schema tabelle e indici verificato con successo.")
    
    print("\n---> [FASE 2/4] Importazione Catalogo Master, Codici Legacy ed Equivalenze...")
    run_catalog(db_url)
    
    print("\n---> [FASE 3/4] Migrazione Storico Acquisti Fornitori da SQLite...")
    migrate_invoices(target_db_url=db_url)
    
    print("\n---> [FASE 4/4] Ingestione Fatture Clienti (2019-2026)...")
    import_all_customer_invoices(db_url)
    
    elapsed = time.time() - start_time
    session = get_db_session()
    
    print(f"\n=======================================================")
    print(f"   MIGRAZIONE COMPLETATA CON SUCCESSO IN {elapsed:.1f} SECONDI!")
    print(f"=======================================================")
    print(f"• Articoli Master:            {session.query(Product).count():,}")
    print(f"• Mappature Legacy N:1:       {session.query(ProductLegacyCode).count():,}")
    print(f"• Equivalenze Fornitori:      {session.query(SupplierProduct).count():,}")
    print(f"• Fornitori Registrati:       {session.query(Supplier).count():,}")
    print(f"• Fatture Acquisto Fornitori: {session.query(Invoice).count():,}")
    print(f"• Righe Acquisto Fornitori:   {session.query(InvoiceItem).count():,}")
    print(f"• Clienti Registrati:         {session.query(Customer).count():,}")
    print(f"• Fatture Vendita Clienti:    {session.query(SalesInvoice).count():,}")
    print(f"• Righe Vendita Clienti:      {session.query(SalesInvoiceItem).count():,}")
    print(f"=======================================================\n")
    session.close()

if __name__ == "__main__":
    main()
