"""
Script per l'importazione iniziale o massiva di tutti i listini prezzi da B-Kode Cloud (bkode.cloud).
Estrae:
- 177 Listini di acquisto fornitori (lisforList) e oltre 5.200 voci articolo (lisforListR) con sconti e prezzi netti
- 4 Listini di vendita clienti (liscliList) e oltre 2.300 voci articolo (liscliListR)
Salva i dati nelle tabelle PostgreSQL:
- price_lists
- price_list_items
- aggiorna Product.list_price se assente
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Forza unbuffered output per visualizzazione in tempo reale
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_db_session, PriceList, PriceListItem, Product, Supplier, Customer, SyncStatus
from app.utils.bkode_client import BKodeClient
from app.utils.settings import SettingsManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BKodeImport")

def parse_args():
    parser = argparse.ArgumentParser(description="Importa tutti i listini prezzi da B-Kode Cloud su PostgreSQL.")
    parser.add_argument("--user", help="Nome utente B-Kode (default da settings.json o ma002)")
    parser.add_argument("--passwd", help="Password B-Kode")
    parser.add_argument("--cookie", help="Cookie ci_session attivo")
    parser.add_argument("--limit-items", type=int, default=15000, help="Limite voci per listino")
    return parser.parse_args()

def main():
    args = parse_args()
    settings = SettingsManager()

    username = args.user or settings.get_bkode_username() or "ma002"
    password = args.passwd or settings.get_bkode_password()
    cookie = args.cookie or settings.get_bkode_cookie()

    print("=" * 70)
    print("  IMPORTAZIONE MASSIVA LISTINI PREZZI DA B-KODE CLOUD")
    print("=" * 70)
    print(f"Utente: {username}")
    print(f"Cookie salvato: {'Presente' if cookie else 'Assente'}")
    print(f"Password: {'Presente' if password else 'Assente'}")
    print("-" * 70)

    client = BKodeClient(username=username, password=password, cookie=cookie)

    # 1. Autenticazione
    authenticated = False
    if cookie:
        print("--> Verifica cookie di sessione esistente...")
        client._apply_cookie(cookie)
        if client.ensure_authenticated():
            print("  [OK] Sessione attiva e funzionante.")
            authenticated = True
        else:
            print("  [!] Cookie non valido o scaduto.")

    if not authenticated and password:
        print(f"--> Tento login con utente '{username}'...")
        if client.login(username, password):
            print("  [OK] Login effettuato con successo!")
            authenticated = True
        else:
            print("  [ERRORE] Login fallito. Verifica username e password.")

    if not authenticated:
        print("\n[ERRORE CRITICO] Impossibile autenticarsi su B-Kode.")
        print("Specifica una password valida con --passwd 'tua_password' oppure un cookie aggiornato con --cookie '...'")
        sys.exit(1)

    session = get_db_session()

    try:
        # ==============================================================
        # PARTE 1: LISTINI ACQUISTO FORNITORI (lisforList / lisforListR)
        # ==============================================================
        print("\n--- 1. Estrazione Testate Listini Acquisto Fornitori (lisforList) ---")
        p_lists = client.fetch_purchase_price_lists(limit=300)
        print(f"  Trovati {len(p_lists)} listini di acquisto.")

        lists_created = 0
        lists_updated = 0

        for pl in p_lists:
            b_id = int(pl.get("lit_id") or 0)
            if not b_id:
                continue

            db_pl = session.query(PriceList).filter_by(bkode_id=b_id).first()
            if not db_pl:
                db_pl = PriceList(bkode_id=b_id, list_type="PURCHASE")
                session.add(db_pl)
                lists_created += 1
            else:
                lists_updated += 1

            db_pl.code = pl.get("lit_code") or ""
            db_pl.description = pl.get("lit_des") or ""
            db_pl.partner_name = pl.get("for_ragsoc_1") or ""
            db_pl.currency = pl.get("lit_codval") or "EUR"
            db_pl.status = "ATTIVO" if pl.get("lit_status") == "A" else "CHIUSO"

            try:
                db_pl.valid_from = datetime.strptime(pl.get("lit_dt_ini"), "%Y-%m-%d").date() if pl.get("lit_dt_ini") else None
                db_pl.valid_to = datetime.strptime(pl.get("lit_dt_fin"), "%Y-%m-%d").date() if pl.get("lit_dt_fin") else None
            except Exception:
                pass

            if db_pl.partner_name:
                supp = session.query(Supplier).filter(Supplier.name.ilike(db_pl.partner_name)).first()
                if supp:
                    db_pl.supplier_id = supp.id

        session.commit()
        print(f"  Salvati {lists_created} nuovi listini acquisto, {lists_updated} aggiornati.")

        # Mappatura bkode_id -> DB id
        bkode_to_db_id = {pl.bkode_id: pl.id for pl in session.query(PriceList).filter_by(list_type="PURCHASE").all()}

        print("\n--- 2. Estrazione Righe Articolo Listini Acquisto (lisforListR) ---")
        p_items = client.fetch_purchase_price_list_items(limit=args.limit_items)
        print(f"  Estratte {len(p_items)} righe articolo per acquisti.")

        items_saved = 0
        for it in p_items:
            art_code = (it.get("lid_art") or "").strip()
            if not art_code or art_code == ".":
                continue

            lit_id = int(it.get("lid_lit_id") or 0)
            db_pl_id = bkode_to_db_id.get(lit_id)
            if not db_pl_id:
                continue

            db_item = session.query(PriceListItem).filter_by(
                price_list_id=db_pl_id, product_code=art_code
            ).first()

            if not db_item:
                db_item = PriceListItem(price_list_id=db_pl_id, product_code=art_code)
                session.add(db_item)

            db_item.description = it.get("_combo_lid_art") or it.get("art_des") or ""
            db_item.drawing_number = it.get("art_n_d") or ""
            db_item.unit_measure = it.get("lid_um") or "NR"

            prz = float(it.get("lid_prz_1") or 0.0)
            sc1 = float(it.get("lid_sc_1_1") or 0.0)
            sc2 = float(it.get("lid_sc_1_2") or 0.0)
            sc3 = float(it.get("lid_sc_1_3") or 0.0)
            net = prz * (1.0 - sc1 / 100.0) * (1.0 - sc2 / 100.0) * (1.0 - sc3 / 100.0)

            db_item.base_price = prz
            db_item.discount_1 = sc1
            db_item.discount_2 = sc2
            db_item.discount_3 = sc3
            db_item.net_price = net

            prod = session.query(Product).filter(Product.code.ilike(art_code)).first()
            if prod:
                db_item.product_id = prod.id

            items_saved += 1
            if items_saved % 500 == 0:
                session.commit()
                print(f"    ... elaborate {items_saved} righe acquisto ...")

        session.commit()
        print(f"  [OK] Elaborate e salvate con successo {items_saved} voci articolo nei listini acquisto.")

        # ==============================================================
        # PARTE 2: LISTINI VENDITA CLIENTI (liscliList / liscliListR)
        # ==============================================================
        print("\n--- 3. Estrazione Testate Listini Vendita Clienti (liscliList) ---")
        s_lists = client.fetch_sales_price_lists(limit=100)
        print(f"  Trovati {len(s_lists)} listini di vendita.")

        s_lists_created = 0
        for sl in s_lists:
            v_id = int(sl.get("vlt_id") or 0)
            if not v_id:
                continue

            db_sl = session.query(PriceList).filter_by(bkode_id=v_id).first()
            if not db_sl:
                db_sl = PriceList(bkode_id=v_id, list_type="SALE")
                session.add(db_sl)
                s_lists_created += 1

            db_sl.code = sl.get("vlt_code") or ""
            db_sl.description = sl.get("vlt_des") or ""
            db_sl.partner_name = sl.get("cli_ragsoc_1") or "Listino Generale"
            db_sl.currency = sl.get("vlt_codval") or "EUR"
            db_sl.status = "ATTIVO" if sl.get("vlt_status") == "A" else "CHIUSO"

            try:
                db_sl.valid_from = datetime.strptime(sl.get("vlt_dt_ini"), "%Y-%m-%d").date() if sl.get("vlt_dt_ini") else None
                db_sl.valid_to = datetime.strptime(sl.get("vlt_dt_fin"), "%Y-%m-%d").date() if sl.get("vlt_dt_fin") else None
            except Exception:
                pass

        session.commit()
        print(f"  Salvati {s_lists_created} nuovi listini vendita.")

        bkode_sales_to_db = {pl.bkode_id: pl.id for pl in session.query(PriceList).filter_by(list_type="SALE").all()}

        print("\n--- 4. Estrazione Righe Articolo Listini Vendita (liscliListR) ---")
        s_items = client.fetch_sales_price_list_items(limit=args.limit_items)
        print(f"  Estratte {len(s_items)} righe articolo per vendite.")

        s_items_saved = 0
        for it in s_items:
            art_code = (it.get("lir_art") or "").strip()
            if not art_code or art_code == ".":
                continue

            vlt_id = int(it.get("lir_vlt_id") or 0)
            db_sl_id = bkode_sales_to_db.get(vlt_id)
            if not db_sl_id:
                continue

            db_item = session.query(PriceListItem).filter_by(
                price_list_id=db_sl_id, product_code=art_code
            ).first()

            if not db_item:
                db_item = PriceListItem(price_list_id=db_sl_id, product_code=art_code)
                session.add(db_item)

            prz = float(it.get("lir_prz_1") or 0.0)
            sc1 = float(it.get("lir_sc_1_1") or 0.0)
            sc2 = float(it.get("lir_sc_1_2") or 0.0)
            net = prz * (1.0 - sc1 / 100.0) * (1.0 - sc2 / 100.0)

            db_item.base_price = prz
            db_item.discount_1 = sc1
            db_item.discount_2 = sc2
            db_item.net_price = net

            prod = session.query(Product).filter(Product.code.ilike(art_code)).first()
            if prod:
                db_item.product_id = prod.id
                if not prod.list_price or prod.list_price == 0.0:
                    prod.list_price = prz

            s_items_saved += 1
            if s_items_saved % 500 == 0:
                session.commit()
                print(f"    ... elaborate {s_items_saved} righe vendita ...")

        session.commit()
        print(f"  [OK] Elaborate e salvate con successo {s_items_saved} voci articolo nei listini vendita.")

        # Aggiorna SyncStatus su DB
        status_rec = session.query(SyncStatus).filter_by(task_name="PRICELISTS").first()
        if not status_rec:
            status_rec = SyncStatus(task_name="PRICELISTS")
            session.add(status_rec)
        status_rec.status = "SUCCESS"
        status_rec.last_sync_time = datetime.utcnow()
        status_rec.items_synced = items_saved + s_items_saved
        status_rec.executed_by_host = os.environ.get("COMPUTERNAME", "CLI")
        session.commit()

        print("\n" + "=" * 70)
        print("  IMPORTAZIONE COMPLETATA CON SUCCESSO!")
        print(f"  • Listini Fornitore: {len(p_lists)} | Voci: {items_saved}")
        print(f"  • Listini Cliente:   {len(s_lists)} | Voci: {s_items_saved}")
        print("=" * 70)

    except Exception as e:
        session.rollback()
        logger.error(f"Errore durante l'importazione: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    main()
