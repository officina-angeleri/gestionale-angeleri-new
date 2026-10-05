"""
Script per scaricare e popolare in massa le righe articolo (InvoiceItem) 
per tutti i FORNITORI TECNICI, PRODUTTIVI e RICAMBISTI da B-Kode Cloud nel DB PostgreSQL.
Esclude utenze, autostrade, carburanti, telefonia, banche e servizi generali.
"""

import sys
import os
import re
import time
from datetime import datetime

sys.path.insert(0, '.')

from app.database import get_db_session, Supplier, Invoice, InvoiceItem, Product, PriceList
from app.utils.bkode_client import BKodeClient
from app.controllers.invoice_manager import InvoiceManager, SUPPLIER_ALIASES

# Parole chiave per escludere fornitori di servizi/utenze/personali
SERVICE_KEYWORDS = [
    "AUTOSTRADE", "TELEPASS", "GLS", "DHL", "POSTE", "SPEDIZION", "AUTOTRASPORT",
    "ENERGIA", "GAS", "LUCE", "ACQUE", "TIM", "VODAFONE", "WIND", "FASTWEB", "TELECOM",
    "KUWAIT", "ENI", "Q8", "ESSO", "IP", "PETROL", "CARBURANT", "LEASING", "NOLEGGIO",
    "BANCA", "BPER", "INTESA", "UNICREDIT", "STUDIO SOCCI", "COMMERCIALIST", "CONSULENZ",
    "TRATTORIA", "RISTORANT", "PIZZERIA", "CAFFETTERIA", "HOTEL", "LIDL", "ESSELUNGA",
    "AMAZON", "SELLMAT", "ROCOCO", "MERCEDES-BENZ", "NORAUTO", "FIERA MILANO", "AUTODESK",
    "SELLA LEASING"
]

# Fornitori Tecnici / Produttivi prioritari e principali
TECHNICAL_SUPPLIERS = [
    # Metalli, profilati e alluminio
    "BARATE", "ALUSIC", "ELVINOX", "ALMET", "SIDERCOM", "TRAFITAL",
    # Lavorazioni meccaniche, tornitura, fresatura, fusioni
    "ENOLA", "MATTI", "PROMETAL", "T.G.P.", "TGP", "FIRPO", "FERRARIO", "I.M.B.G.", "IMBG", "INGRAMEC", "FIM", "OMEGA",
    # Pneumatica, automazione, motori, riduttori, cuscinetti
    "METAL WORK", "CARPANELLI", "TRAMEC", "CASA DEL CUSCINETTO", "TECHNOBI", "PANASONIC", "INOVANCE",
    # Elettrotecnica, cavi, componentistica industriale
    "COMEL", "M.G.M.", "SACCHI", "CIGNOLI", "DETAS",
    # Trattamenti superficiali, verniciatura
    "PARRINO", "GAMBOLESE", "VAL SPRAY",
    # Utensileria e minuteria
    "CENTRO TECNOLOGICO UTENSILI", "MILESI UTENSILI", "BONORA"
]

def is_service_supplier(name: str) -> bool:
    upper = name.upper()
    return any(k in upper for k in SERVICE_KEYWORDS)

def is_technical_supplier(name: str) -> bool:
    upper = name.upper()
    if is_service_supplier(name):
        return False
    return any(k in upper for k in TECHNICAL_SUPPLIERS)

def merge_supplier_duplicates(session):
    """Unifica i fornitori duplicati noti (es. BARATE', ALUSIC, ELVINOX, FIRPO, OMEGA)."""
    print("\n--- 1. Verifica ed eventuale unificazione fornitori duplicati ---")
    suppliers = session.query(Supplier).all()
    merged_total = 0

    for supp in suppliers:
        canonical = InvoiceManager._normalize_supplier(supp.name)
        if canonical != supp.name:
            target = session.query(Supplier).filter(Supplier.name == canonical).first()
            if target and target.id != supp.id:
                print(f"  Unisco ID={supp.id} ('{supp.name}') in ID={target.id} ('{target.name}')...")
                # Riassegna listini e prodotti
                session.query(PriceList).filter_by(supplier_id=supp.id).update({"supplier_id": target.id})
                session.query(Product).filter_by(default_supplier_id=str(supp.id)).update({"default_supplier_id": str(target.id)})

                invs = session.query(Invoice).filter_by(supplier_id=supp.id).all()
                for inv in invs:
                    dup = session.query(Invoice).filter_by(
                        supplier_id=target.id, number=inv.number, date=inv.date
                    ).first()
                    if dup:
                        inv_items = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()
                        dup_items = session.query(InvoiceItem).filter_by(invoice_id=dup.id).count()
                        if inv_items > 0 and dup_items == 0:
                            session.query(InvoiceItem).filter_by(invoice_id=dup.id).delete()
                            session.delete(dup)
                            inv.supplier_id = target.id
                        else:
                            session.query(InvoiceItem).filter_by(invoice_id=inv.id).delete()
                            session.delete(inv)
                    else:
                        inv.supplier_id = target.id
                session.commit()
                session.delete(supp)
                session.commit()
                merged_total += 1

    print(f"Completata unificazione duplicati: {merged_total} fornitori accorpati.")

def sync_technical_suppliers():
    print("=" * 75)
    print("  SINCRONIZZAZIONE ARTICOLI FATTURE FORNITORI TECNICI DA B-KODE")
    print("=" * 75)

    session = get_db_session()
    merge_supplier_duplicates(session)

    client = BKodeClient()
    if not client.ensure_authenticated():
        print("[ERRORE] Autenticazione B-Kode Cloud fallita.")
        return

    # Trova tutti i fornitori tecnici a DB
    suppliers = session.query(Supplier).order_by(Supplier.name).all()
    target_suppliers = [s for s in suppliers if is_technical_supplier(s.name)]
    print(f"\nTrovati {len(target_suppliers)} fornitori tecnici nel catalogo gestionale.")

    inv_mgr = InvoiceManager()
    base_nas_dir = r"\\angeleri_new\Pubblica\Database\Fornitori"
    use_nas = os.path.exists(base_nas_dir)
    print(f"Destinazione file XML: {'Server NAS (' + base_nas_dir + ')' if use_nas else 'Cartella locale (data/Fornitori)'}")

    total_downloaded = 0
    total_parsed_invoices = 0
    total_items_created = 0

    for idx, supp in enumerate(target_suppliers, 1):
        # Fatture di questo fornitore senza articoli
        invs = session.query(Invoice).filter_by(supplier_id=supp.id).order_by(Invoice.date.desc()).all()
        zero_items_invs = [inv for inv in invs if session.query(InvoiceItem).filter_by(invoice_id=inv.id).count() == 0]
        
        if not zero_items_invs:
            continue

        print(f"\n[{idx}/{len(target_suppliers)}] {supp.name} (ID: {supp.id}) -> {len(zero_items_invs)} / {len(invs)} fatture senza articoli")

        # Cerca cartella sul server
        safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', supp.name.split()[0]).strip('_')
        if use_nas:
            cand_dirs = [d for d in os.listdir(base_nas_dir) if safe_name.lower() in d.lower()]
            supp_dir = os.path.join(base_nas_dir, cand_dirs[0]) if cand_dirs else os.path.join(base_nas_dir, safe_name)
        else:
            supp_dir = os.path.join(os.getcwd(), "data", "Fornitori", safe_name)

        try:
            os.makedirs(supp_dir, exist_ok=True)
        except Exception:
            pass

        # Estrai la mappa fxml_id da B-Kode per questo fornitore
        bkode_invoices = {}
        # Cerca per nome fornitore su fatforxmlList
        search_term = supp.name.replace("S.P.A.", "").replace("S.R.L.", "").replace("SPA", "").replace("SRL", "").strip().split()[0]
        start = 0
        limit = 200
        while True:
            res = client._post_grid('fatforxmlList', {
                'filter': f'[{{"field": "fxml_ragsoc_1", "data": {{"type": "string", "value": "{search_term}"}}}}]',
                'start': str(start), 'limit': str(limit)
            })
            if not res or not res.get('items'):
                break
            for pinv in res['items']:
                num = str(pinv.get("fxml_nr_fat") or "").strip()
                dt_str = pinv.get("fxml_dt_fat") or ""
                fid = pinv.get("fxml_id")
                fn = pinv.get("fxml_file") or pinv.get("fxml_file_sdi") or ""
                if num and dt_str and fid:
                    dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                    bkode_invoices[(num, dt)] = {"fxml_id": fid, "file_name": fn}
                    # Anche con match solo su numero
                    bkode_invoices[num] = {"fxml_id": fid, "file_name": fn}
            if len(res['items']) < limit:
                break
            start += limit

        # Elabora le fatture mancanti
        supp_success = 0
        for inv in zero_items_invs:
            bkode_data = bkode_invoices.get((inv.number, inv.date)) or bkode_invoices.get(inv.number)
            fxml_id = bkode_data.get("fxml_id") if bkode_data else None
            file_name = (bkode_data.get("file_name") if bkode_data else None) or inv.file_path or f"{supp.id}_{inv.number.replace('/', '_')}.xml"
            if not file_name.lower().endswith(".xml"):
                file_name += ".xml"

            xml_path = os.path.join(supp_dir, file_name)

            if not os.path.exists(xml_path):
                if not fxml_id:
                    continue
                content = client.download_purchase_invoice_xml(fxml_id, file_name)
                if content:
                    try:
                        with open(xml_path, 'wb') as f:
                            f.write(content)
                        total_downloaded += 1
                    except Exception as fe:
                        print(f"    Errore salvataggio {file_name}: {fe}")
                        continue
                else:
                    continue

            # Parsing e ingestione articoli
            try:
                inv.file_path = xml_path
                session.commit()
                imported = inv_mgr.import_invoice(xml_path)
                item_cnt = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()
                if item_cnt > 0:
                    supp_success += 1
                    total_parsed_invoices += 1
                    total_items_created += item_cnt
            except Exception as e:
                print(f"    Errore importazione fattura {inv.number}: {e}")

        if supp_success > 0:
            print(f"  -> Recuperate {supp_success} fatture con successo!")

    print("\n" + "=" * 75)
    print("  RIEPILOGO FINALE RECUPERO FORNITORI TECNICI")
    print("=" * 75)
    print(f"File XML scaricati: {total_downloaded}")
    print(f"Fatture completate con articoli: {total_parsed_invoices}")
    print(f"Righe articolo / ricambi inseriti a DB: {total_items_created}")

if __name__ == "__main__":
    sync_technical_suppliers()
