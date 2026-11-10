import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_db_session, Supplier, Invoice, InvoiceItem
from app.utils.bkode_client import BKodeClient
from app.controllers.invoice_manager import InvoiceManager

def sync_linak():
    session = get_db_session()
    supp = session.query(Supplier).filter(Supplier.name.ilike('%LINAK%')).first()
    if not supp:
        print("Supplier LINAK not found in DB")
        return
    print(f"Found supplier: {supp.name} (ID: {supp.id})")

    invs = session.query(Invoice).filter_by(supplier_id=supp.id).order_by(Invoice.date.desc()).all()
    zero_items_invs = [inv for inv in invs if session.query(InvoiceItem).filter_by(invoice_id=inv.id).count() == 0]
    print(f"Total invoices: {len(invs)}, invoices without items: {len(zero_items_invs)}")

    client = BKodeClient()
    if not client.ensure_authenticated():
        print("[ERRORE] Autenticazione B-Kode fallita.")
        return
    print("B-Kode autenticato con successo!")

    base_nas_dir = r"\\angeleri_new\Pubblica\Database\Fornitori"
    use_nas = os.path.exists(base_nas_dir)
    supp_dir = os.path.join(base_nas_dir, "LINAK") if use_nas else os.path.join(os.getcwd(), "data", "Fornitori", "LINAK")
    os.makedirs(supp_dir, exist_ok=True)
    print("Cartella salvataggio XML:", supp_dir)

    # Cerca fatture LINAK su B-Kode
    bkode_invoices = {}
    start = 0
    limit = 200
    while True:
        res = client._post_grid('fatforxmlList', {
            'filter': '[{"field": "fxml_ragsoc_1", "data": {"type": "string", "value": "LINAK"}}]',
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
                bkode_invoices[num] = {"fxml_id": fid, "file_name": fn}
        if len(res['items']) < limit:
            break
        start += limit

    print(f"Fatture trovate su B-Kode per LINAK: {len(bkode_invoices)}")

    inv_mgr = InvoiceManager()
    downloaded = 0
    parsed = 0
    items_total = 0

    for inv in zero_items_invs:
        bkode_data = bkode_invoices.get((inv.number, inv.date)) or bkode_invoices.get(inv.number)
        fxml_id = bkode_data.get("fxml_id") if bkode_data else None
        file_name = (bkode_data.get("file_name") if bkode_data else None) or inv.file_path or f"LINAK_{inv.number.replace('/', '_')}.xml"
        if not file_name.lower().endswith(".xml"):
            file_name += ".xml"

        xml_path = os.path.join(supp_dir, file_name)
        if not os.path.exists(xml_path):
            if not fxml_id:
                print(f"  [MISSING FXML_ID] {inv.number} del {inv.date}")
                continue
            content = client.download_purchase_invoice_xml(fxml_id, file_name)
            if content:
                with open(xml_path, 'wb') as f:
                    f.write(content)
                downloaded += 1
                print(f"  [SCARICATO] {file_name}")
            else:
                print(f"  [ERRORE DOWNLOAD] {file_name}")
                continue

        # Parsing XML e ingestione articoli
        try:
            inv.file_path = xml_path
            session.commit()
            imported = inv_mgr.import_invoice(xml_path)
            item_cnt = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()
            print(f"  [PARSED] Fattura {inv.number}: {item_cnt} righe create")
            parsed += 1
            items_total += item_cnt
        except Exception as e:
            print(f"  [ERRORE PARSING] {inv.number}: {e}")

    print(f"\nCompletato! Scaricati: {downloaded}, Parsati: {parsed}, Righe create: {items_total}")

if __name__ == "__main__":
    sync_linak()
