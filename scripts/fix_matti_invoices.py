"""
Script per riparare e completare tutte le fatture di MATTI:
1. Normalizza il fornitore Matti (unisce ID 317 'MATTI S.r.l.' in ID 308 'MATTI SRL OFFICINE MECCANICHE').
2. Rimuove i record testata duplicati.
3. Riassegna le fatture 2026 mancanti a ID 308.
4. Rimuove il fornitore duplicato ID 317.
5. Scarica da B-Kode Cloud i file XML mancanti direttamente nella cartella di rete:
   //angeleri_new/Pubblica/Database/Fornitori/Matti/
6. Esegue il parsing SDI per popolare tutte le righe articolo (InvoiceItem) e collegare i codici prodotto.
"""

import sys
import os
import base64
from datetime import datetime

sys.path.insert(0, '.')

from app.database import get_db_session, Supplier, Invoice, InvoiceItem
from app.utils.bkode_client import BKodeClient
from app.controllers.invoice_manager import InvoiceManager

def run_fix():
    print("=" * 70)
    print("  RIPARAZIONE E COMPLETAMENTO FATTURE MATTI")
    print("=" * 70)

    session = get_db_session()
    supp_308 = session.query(Supplier).filter_by(id=308).first()
    supp_317 = session.query(Supplier).filter_by(id=317).first()

    if not supp_308:
        print("[ERRORE] Fornitore ID 308 non trovato!")
        return

    print(f"Fornitore Principale ID 308: {supp_308.name} (P.IVA: {supp_308.piva})")
    if supp_317:
        print(f"Fornitore Duplicato ID 317: {supp_317.name}")
    else:
        print("Fornitore ID 317 gia' rimosso o assente.")

    # 1. Unione 317 -> 308
    if supp_317:
        invs_317 = session.query(Invoice).filter_by(supplier_id=317).all()
        print(f"\nFatture attualmente sotto ID 317: {len(invs_317)}")

        merged_count = 0
        deleted_duplicates = 0

        for inv in invs_317:
            # Verifica se esiste già la stessa fattura sotto 308
            existing_in_308 = session.query(Invoice).filter_by(
                supplier_id=308, number=inv.number, date=inv.date
            ).first()

            if existing_in_308:
                # E' un duplicato testata: eliminiamo il record in 317
                session.delete(inv)
                deleted_duplicates += 1
            else:
                # E' una fattura nuova (es. 2026): riassegnamo a 308
                inv.supplier_id = 308
                merged_count += 1

        session.commit()
        print(f"  -> {deleted_duplicates} testate duplicate eliminate da ID 317.")
        print(f"  -> {merged_count} fatture 2026 riassegnate con successo a ID 308.")

        # Elimina il fornitore 317
        session.delete(supp_317)
        session.commit()
        print("  -> Fornitore ID 317 eliminato definitivamente.")

    # 2. Verifica fatture sotto 308 che non hanno righe articolo
    invs_without_items = []
    all_308 = session.query(Invoice).filter_by(supplier_id=308).order_by(Invoice.date.desc()).all()
    print(f"\nTotale fatture ora collegate a MATTI (ID 308): {len(all_308)}")

    for inv in all_308:
        items_cnt = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()
        if items_cnt == 0:
            invs_without_items.append(inv)

    print(f"Fatture senza righe articolo (da scaricare / parsare): {len(invs_without_items)}")
    for inv in invs_without_items:
        print(f"  - Nr: {inv.number} del {inv.date} (file_path: {inv.file_path})")

    # 3. Download XML da B-Kode e parsing
    client = BKodeClient()
    if not client.ensure_authenticated():
        print("[ERRORE] Autenticazione B-Kode fallita.")
        return

    # Mappa delle fatture su B-Kode per MATTI
    print("\n--> Interrogo B-Kode fatforxmlList per trovare gli fxml_id di MATTI...")
    bkode_matti = {}
    start = 0
    limit = 500
    while True:
        res = client._post_grid('fatforxmlList', {'start': str(start), 'limit': str(limit)})
        if not res or not res.get('items'):
            break
        for pinv in res['items']:
            s_name = (pinv.get("fxml_ragsoc_1") or pinv.get("for_ragsoc_1") or "").upper()
            if "MATTI" in s_name:
                num = str(pinv.get("fxml_nr_fat") or "").strip()
                dt_str = pinv.get("fxml_dt_fat") or ""
                fxml_id = pinv.get("fxml_id")
                fxml_file = pinv.get("fxml_file") or pinv.get("fxml_file_sdi") or ""
                if num and dt_str and fxml_id:
                    dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                    bkode_matti[(num, dt)] = {
                        "fxml_id": fxml_id,
                        "file_name": fxml_file,
                        "tot": float(pinv.get("fxml_tot") or 0.0)
                    }
        if len(res['items']) < limit:
            break
        start += limit

    print(f"Trovate {len(bkode_matti)} fatture totali per MATTI su B-Kode Cloud.")

    # Cartella di destinazione XML di Matti
    target_dir = r"\\angeleri_new\Pubblica\Database\Fornitori\Matti"
    if not os.path.exists(target_dir):
        # Fallback locale se non raggiungibile
        target_dir = os.path.join(os.getcwd(), "data", "Fornitori", "Matti")
        os.makedirs(target_dir, exist_ok=True)
    print(f"Cartella salvataggio XML: {target_dir}")

    inv_mgr = InvoiceManager()

    # Per ogni fattura senza righe articolo, scarica e importa
    for inv in invs_without_items:
        key = (inv.number, inv.date)
        bkode_info = bkode_matti.get(key)
        if not bkode_info:
            print(f"[AVVISO] Fattura {inv.number} del {inv.date} non trovata nei metadati B-Kode.")
            continue

        fxml_id = bkode_info["fxml_id"]
        file_name = bkode_info["file_name"] or inv.file_path or f"matti_{inv.number.replace('/', '_')}.xml"
        if not file_name.lower().endswith(".xml"):
            file_name += ".xml"

        xml_path = os.path.join(target_dir, file_name)

        if not os.path.exists(xml_path):
            print(f"  -> Scarico XML da B-Kode: fxml_id={fxml_id} ({file_name})...")
            content = client.download_purchase_invoice_xml(fxml_id, file_name)
            if not content:
                # Prova con chiamata diretta URL
                b64_file = base64.b64encode(file_name.encode('utf-8')).decode('utf-8')
                url = f"{client.BASE_URL}/panel/attachment/angeleri/show/fatforxmlList/fxml_file/{fxml_id}/grid/{b64_file}"
                r = client.session.get(url, timeout=30)
                if r.status_code == 200 and len(r.content) > 100:
                    content = r.content

            if content:
                with open(xml_path, 'wb') as f:
                    f.write(content)
                print(f"     Salvato: {xml_path} ({len(content)} bytes)")
            else:
                print(f"     [ERRORE] Impossibile scaricare XML per {inv.number}")
                continue
        else:
            print(f"  -> File XML gia' presente sul disco: {xml_path}")

        # Aggiorna il percorso del file nella testata fattura se diverso
        inv.file_path = xml_path
        session.commit()

        # Esegui il parsing e l'importazione delle righe
        print(f"  -> Ingestione articoli per fattura {inv.number}...")
        inv_mgr.import_invoice(xml_path)

    # 4. Verifica finale
    final_invoices = session.query(Invoice).filter_by(supplier_id=308).order_by(Invoice.date.desc()).all()
    print("\n" + "=" * 70)
    print(f"VERIFICA FINALE MATTI (ID 308): {len(final_invoices)} fatture")
    print("=" * 70)
    total_items = 0
    for inv in final_invoices:
        cnt = session.query(InvoiceItem).filter_by(invoice_id=inv.id).count()
        total_items += cnt
        if inv.date.year >= 2026 or cnt == 0:
            print(f"  Fattura {inv.number:10} del {inv.date} | Tot: € {inv.total_amount:10.2f} | Righe Articolo: {cnt}")

    print(f"\nTOTALE COMPLESSIVO RIGHE ARTICOLO MATTI: {total_items}")

if __name__ == "__main__":
    run_fix()
