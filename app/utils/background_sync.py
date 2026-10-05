"""
Modulo di sincronizzazione periodica distribuita con B-Kode per rete multi-client.
Utilizza PostgreSQL Advisory Lock (pg_try_advisory_lock) per garantire l'elezione dinamica
di un singolo nodo Master ed evitare chiamate duplicate o conflitti di scrittura tra diverse
postazioni dell'officina.
"""

import os
import socket
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import text
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from app.database import (
    get_db_session, PriceList, PriceListItem, Product, Supplier, 
    Customer, SyncStatus, Invoice, InvoiceItem, SalesInvoice, SalesInvoiceItem
)
from app.utils.bkode_client import BKodeClient

logger = logging.getLogger(__name__)

# ID numerico univoco per il lock distribuito PostgreSQL (scelto arbitrariamente per Gestionale Angeleri)
POSTGRES_SYNC_LOCK_ID = 777888

def try_acquire_sync_lock(session) -> bool:
    """Tenta di acquisire il lock distribuito a livello di database PostgreSQL."""
    try:
        res = session.execute(text(f"SELECT pg_try_advisory_lock({POSTGRES_SYNC_LOCK_ID});")).scalar()
        return bool(res)
    except Exception as e:
        logger.warning(f"[SyncLock] Errore richiesta advisory lock: {e}")
        return False

def release_sync_lock(session) -> bool:
    """Rilascia il lock distribuito PostgreSQL."""
    try:
        res = session.execute(text(f"SELECT pg_advisory_unlock({POSTGRES_SYNC_LOCK_ID});")).scalar()
        return bool(res)
    except Exception as e:
        logger.warning(f"[SyncLock] Errore rilascio advisory lock: {e}")
        return False


class BKodeSyncEngine:
    """Motore di sincronizzazione dati B-Kode -> PostgreSQL."""

    def __init__(self, client: Optional[BKodeClient] = None):
        self.client = client or BKodeClient()
        self.hostname = socket.gethostname()

    def sync_all(self, force: bool = False, min_interval_minutes: int = 15) -> Dict[str, Any]:
        """
        Esegue la sincronizzazione completa (Listini, Articoli, Fatture) se eletto Master.
        Se un altro PC sta già eseguendo il controllo o l'ultimo sync è recente, esce senza errori.
        """
        session = get_db_session()
        summary = {
            "executed": False,
            "reason": "",
            "price_lists_synced": 0,
            "price_items_synced": 0,
            "products_synced": 0,
            "invoices_synced": 0,
            "errors": []
        }

        # 1. Tenta acquisizione lock distribuito su PostgreSQL
        if not try_acquire_sync_lock(session):
            summary["reason"] = "Un'altra postazione in officina sta già eseguendo la sincronizzazione B-Kode."
            logger.info(f"[Sync] {summary['reason']}")
            session.close()
            return summary

        try:
            # 2. Verifica se il controllo è già avvenuto recentemente (a meno di forzatura manuale)
            if not force:
                recent_sync = session.query(SyncStatus).filter(
                    SyncStatus.last_sync_time >= datetime.utcnow() - timedelta(minutes=min_interval_minutes)
                ).first()
                if recent_sync:
                    summary["reason"] = f"Ultima sincronizzazione recente ({recent_sync.last_sync_time.strftime('%H:%M:%S')} da {recent_sync.executed_by_host})."
                    logger.info(f"[Sync] {summary['reason']}")
                    return summary

            logger.info(f"[Sync] Nodo eletto Master: {self.hostname}. Verifica credenziali B-Kode...")

            # Assicura autenticazione attiva
            if not self.client.ensure_authenticated():
                summary["executed"] = False
                summary["reason"] = "Credenziali B-Kode mancanti o non valide. Inserisci la password in 'B-Kode Cloud'."
                logger.warning(f"[Sync] {summary['reason']}")
                return summary

            summary["executed"] = True
            logger.info(f"[Sync] Autenticazione riuscita. Avvio sincronizzazione B-Kode...")

            # 3. Sincronizzazione Listini Prezzi (Acquisti & Vendite)
            pl_res = self.sync_price_lists(session)
            summary["price_lists_synced"] = pl_res.get("lists_count", 0)
            summary["price_items_synced"] = pl_res.get("items_count", 0)

            # 4. Sincronizzazione Nuovi Articoli a Catalogo
            prod_res = self.sync_new_products(session)
            summary["products_synced"] = prod_res.get("new_products_count", 0)

            # 5. Sincronizzazione Nuove Fatture (Vendite e Acquisti)
            inv_res = self.sync_recent_invoices(session)
            summary["invoices_synced"] = inv_res.get("invoices_count", 0)

            logger.info(f"[Sync] Sincronizzazione completata da {self.hostname}: {summary}")

        except Exception as e:
            logger.error(f"[Sync] Errore imprevisto durante la sincronizzazione: {e}")
            summary["errors"].append(str(e))
        finally:
            # Rilascia sempre il lock distribuito
            release_sync_lock(session)
            session.close()

        return summary

    def sync_price_lists(self, session) -> Dict[str, Any]:
        """Sincronizza Listini Fornitori (lisforList / lisforListR) e Listini Clienti (liscliList / liscliListR)."""
        logger.info("[Sync] Sincronizzazione listini prezzi da B-Kode...")
        lists_count = 0
        items_count = 0

        # Aggiorna stato SyncStatus
        status_rec = session.query(SyncStatus).filter_by(task_name="PRICELISTS").first()
        if not status_rec:
            status_rec = SyncStatus(task_name="PRICELISTS")
            session.add(status_rec)
        status_rec.status = "RUNNING"
        status_rec.executed_by_host = self.hostname
        session.commit()

        try:
            # A. Listini Acquisto Fornitori
            p_lists = self.client.fetch_purchase_price_lists(limit=250)
            p_items = self.client.fetch_purchase_price_list_items(limit=10000)

            # Mappatura listini per lit_id
            for pl in p_lists:
                b_id = int(pl.get("lit_id") or 0)
                if not b_id:
                    continue
                db_pl = session.query(PriceList).filter_by(bkode_id=b_id).first()
                if not db_pl:
                    db_pl = PriceList(bkode_id=b_id, list_type="PURCHASE")
                    session.add(db_pl)

                db_pl.code = pl.get("lit_code") or ""
                db_pl.description = pl.get("lit_des") or ""
                db_pl.partner_name = pl.get("for_ragsoc_1") or ""
                db_pl.currency = pl.get("lit_codval") or "EUR"
                db_pl.status = "ATTIVO" if pl.get("lit_status") == "A" else "CHIUSO"

                # Date validità
                try:
                    db_pl.valid_from = datetime.strptime(pl.get("lit_dt_ini"), "%Y-%m-%d").date() if pl.get("lit_dt_ini") else None
                    db_pl.valid_to = datetime.strptime(pl.get("lit_dt_fin"), "%Y-%m-%d").date() if pl.get("lit_dt_fin") else None
                except Exception:
                    pass

                # Collega eventuale fornitore nel DB
                if db_pl.partner_name:
                    supp = session.query(Supplier).filter(Supplier.name.ilike(db_pl.partner_name)).first()
                    if supp:
                        db_pl.supplier_id = supp.id

                lists_count += 1
            session.commit()

            # Mappa ID listino bkode -> id DB
            bkode_to_db_id = {pl.bkode_id: pl.id for pl in session.query(PriceList).all()}

            # Inserimento / Aggiornamento righe articoli acquisto
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

                # Collega a Product se presente
                prod = session.query(Product).filter(Product.code.ilike(art_code)).first()
                if prod:
                    db_item.product_id = prod.id

                items_count += 1

            session.commit()

            # B. Listini Vendita Clienti
            s_lists = self.client.fetch_sales_price_lists(limit=50)
            s_items = self.client.fetch_sales_price_list_items(limit=10000)

            for sl in s_lists:
                v_id = int(sl.get("vlt_id") or 0)
                if not v_id:
                    continue
                db_sl = session.query(PriceList).filter_by(bkode_id=v_id, list_type="SALE").first()
                if not db_sl:
                    db_sl = PriceList(bkode_id=v_id, list_type="SALE")
                    session.add(db_sl)

                db_sl.code = sl.get("vlt_code") or ""
                db_sl.description = sl.get("vlt_des") or ""
                db_sl.partner_name = sl.get("cli_ragsoc_1") or "Listino Generale"
                db_sl.currency = sl.get("vlt_codval") or "EUR"
                db_sl.status = "ATTIVO" if sl.get("vlt_status") == "A" else "CHIUSO"
                lists_count += 1
            session.commit()

            # Mappa listini vendita
            bkode_sales_to_db = {pl.bkode_id: pl.id for pl in session.query(PriceList).filter_by(list_type="SALE").all()}

            for it in s_items:
                art_code = (it.get("vld_art") or it.get("art_code") or it.get("lir_art") or "").strip()
                if not art_code or art_code == ".":
                    continue

                vlt_id = int(it.get("vld_vlt_id") or it.get("lir_vlt_id") or 0)
                db_sl_id = bkode_sales_to_db.get(vlt_id)
                if not db_sl_id:
                    continue

                db_item = session.query(PriceListItem).filter_by(
                    price_list_id=db_sl_id, product_code=art_code
                ).first()

                if not db_item:
                    db_item = PriceListItem(price_list_id=db_sl_id, product_code=art_code)
                    session.add(db_item)

                prz = float(it.get("vld_prz_1") or it.get("lir_prz_1") or 0.0)
                sc1 = float(it.get("vld_sc_1_1") or it.get("lir_sc_1_1") or 0.0)
                sc2 = float(it.get("vld_sc_1_2") or it.get("lir_sc_1_2") or 0.0)
                sc3 = float(it.get("vld_sc_1_3") or it.get("lir_sc_1_3") or 0.0)
                net = prz * (1.0 - sc1 / 100.0) * (1.0 - sc2 / 100.0) * (1.0 - sc3 / 100.0)

                db_item.description = (it.get("art_des1") or "").strip()
                db_item.base_price = prz
                db_item.discount_1 = sc1
                db_item.discount_2 = sc2
                db_item.discount_3 = sc3
                db_item.net_price = net

                prod = session.query(Product).filter(Product.code.ilike(art_code)).first()
                if prod:
                    db_item.product_id = prod.id
                    # Se il prodotto non ha listino vendita valorizzato, aggiornalo con il listino ufficiale
                    if not prod.list_price or prod.list_price == 0.0:
                        prod.list_price = prz

                items_count += 1

            session.commit()

            # Aggiorna stato SyncStatus
            status_rec.status = "SUCCESS"
            status_rec.last_sync_time = datetime.utcnow()
            status_rec.items_synced = items_count
            session.commit()

        except Exception as e:
            session.rollback()
            status_rec.status = "ERROR"
            status_rec.last_error = str(e)
            session.commit()
            logger.error(f"[Sync] Errore sincronizzazione listini: {e}")

        return {"lists_count": lists_count, "items_count": items_count}

    def sync_new_products(self, session) -> Dict[str, Any]:
        """Controlla se ci sono nuovi articoli inseriti in B-Kode non presenti nel database locale."""
        logger.info("[Sync] Controllo nuovi articoli a catalogo da B-Kode...")
        new_count = 0
        status_rec = session.query(SyncStatus).filter_by(task_name="PRODUCTS").first()
        if not status_rec:
            status_rec = SyncStatus(task_name="PRODUCTS")
            session.add(status_rec)
        status_rec.status = "RUNNING"
        status_rec.executed_by_host = self.hostname
        session.commit()

        try:
            # Legge gli ultimi 100 articoli inseriti/modificati su B-Kode
            items = self.client.fetch_products(start=0, limit=100)
            for it in items:
                code = (it.get("art_code") or "").strip()
                if not code:
                    continue
                existing = session.query(Product).filter(Product.code.ilike(code)).first()
                if not existing:
                    prod = Product(
                        code=code,
                        name=it.get("art_des") or code,
                        type=it.get("art_tipo") or "ALTRO",
                        category=it.get("art_classe") or "Standard",
                        unit_measure=it.get("art_um") or "NR",
                        bkode_id=int(it.get("art_id") or 0) if it.get("art_id") else None,
                        drawing_number=it.get("art_n_d") or "",
                        conversion_factor=float(it.get("art_cnv_a") or 1.0) if it.get("art_cnv_a") else 1.0,
                        purchase_um=it.get("art_um_a") or ""
                    )
                    session.add(prod)
                    new_count += 1

            session.commit()
            status_rec.status = "SUCCESS"
            status_rec.last_sync_time = datetime.utcnow()
            status_rec.items_synced = new_count
            session.commit()
        except Exception as e:
            session.rollback()
            status_rec.status = "ERROR"
            status_rec.last_error = str(e)
            session.commit()
            logger.error(f"[Sync] Errore sincronizzazione articoli: {e}")

        return {"new_products_count": new_count}

    def sync_recent_invoices(self, session) -> Dict[str, Any]:
        """Controlla se ci sono nuove fatture su B-Kode (Vendite fatcliList e Acquisti fatforxmlList)."""
        logger.info("[Sync] Controllo fatture recenti da B-Kode...")
        invoices_count = 0
        status_rec = session.query(SyncStatus).filter_by(task_name="INVOICES").first()
        if not status_rec:
            status_rec = SyncStatus(task_name="INVOICES")
            session.add(status_rec)
        status_rec.status = "RUNNING"
        status_rec.executed_by_host = self.hostname
        session.commit()

        try:
            # 1. Fatture Vendita Clienti
            sales_invs = self.client.fetch_sales_invoices(start=0, limit=100)
            for inv in sales_invs:
                num = str(inv.get("fat_nr") or inv.get("fat_num") or inv.get("doc_num") or "").strip()
                dt_str = inv.get("fat_dt") or inv.get("doc_dt") or ""
                if not num or not dt_str:
                    continue
                try:
                    dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

                exists = session.query(SalesInvoice).filter_by(number=num, year=dt.year).first()
                if not exists:
                    # Cerca o crea cliente
                    cust_name = (inv.get("cli_ragsoc_1") or "Cliente Sconosciuto").strip()
                    cust = session.query(Customer).filter(Customer.name.ilike(cust_name)).first()
                    if not cust:
                        cust = Customer(name=cust_name)
                        session.add(cust)
                        session.flush()

                    tot = float(inv.get("fat_imp_net") or inv.get("fat_tot_doc") or inv.get("doc_tot") or 0.0)
                    doc_type = inv.get("cau_des") or inv.get("fat_tipo") or "FATTURA"
                    new_inv = SalesInvoice(
                        customer_id=cust.id,
                        number=num,
                        date=dt,
                        year=dt.year,
                        doc_type=doc_type,
                        total_amount=tot
                    )
                    session.add(new_inv)
                    invoices_count += 1

            session.commit()

            # 2. Fatture Elettroniche Acquisto Fornitori
            purch_invs = self.client.fetch_purchase_invoices(start=0, limit=100)
            for pinv in purch_invs:
                num = str(pinv.get("fxml_nr_fat") or pinv.get("xml_num_doc") or pinv.get("doc_num") or "").strip()
                dt_str = pinv.get("fxml_dt_fat") or pinv.get("xml_dt_doc") or pinv.get("doc_dt") or ""
                if not num or not dt_str:
                    continue
                try:
                    dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

                supp_raw = (pinv.get("fxml_ragsoc_1") or pinv.get("for_ragsoc_1") or pinv.get("xml_ced_ragsoc") or "").strip()
                if supp_raw:
                    from app.controllers.invoice_manager import InvoiceManager
                    canonical_name = InvoiceManager._normalize_supplier(supp_raw)
                    supp = session.query(Supplier).filter(Supplier.name.ilike(canonical_name)).first()
                    if not supp:
                        supp = session.query(Supplier).filter(Supplier.name.ilike(supp_raw)).first()
                    if not supp:
                        supp = Supplier(name=canonical_name)
                        session.add(supp)
                        session.flush()

                    exists_p = session.query(Invoice).filter_by(supplier_id=supp.id, number=num, date=dt).first()
                    items_cnt = session.query(InvoiceItem).filter_by(invoice_id=exists_p.id).count() if exists_p else 0

                    if not exists_p or items_cnt == 0:
                        file_name = pinv.get("fxml_file") or pinv.get("fxml_file_sdi") or ""
                        fxml_id = pinv.get("fxml_id")
                        xml_saved_path = None

                        if fxml_id and file_name:
                            base_dir = r"\\angeleri_new\Pubblica\Database\Fornitori"
                            safe_name = supp.name.replace("SRL", "").replace("S.P.A.", "").replace("S.R.L.", "").replace("SPA", "").strip()
                            cand_dirs = [d for d in os.listdir(base_dir) if safe_name.lower() in d.lower()] if os.path.exists(base_dir) else []
                            target_dir = os.path.join(base_dir, cand_dirs[0]) if cand_dirs else (os.path.join(base_dir, safe_name) if os.path.exists(base_dir) else os.path.join(os.getcwd(), "data", "Fornitori", safe_name))
                            try:
                                os.makedirs(target_dir, exist_ok=True)
                            except Exception:
                                pass

                            target_file = file_name if file_name.lower().endswith(".xml") else file_name + ".xml"
                            xml_full_path = os.path.join(target_dir, target_file)

                            if not os.path.exists(xml_full_path):
                                try:
                                    xml_bytes = self.client.download_purchase_invoice_xml(int(fxml_id), file_name)
                                    if xml_bytes:
                                        with open(xml_full_path, "wb") as f:
                                            f.write(xml_bytes)
                                        xml_saved_path = xml_full_path
                                except Exception as err:
                                    logger.warning(f"[Sync] Errore download/salvataggio XML {xml_full_path}: {err}")
                            else:
                                xml_saved_path = xml_full_path

                        if xml_saved_path and os.path.exists(xml_saved_path):
                            try:
                                inv_mgr = InvoiceManager()
                                inv_mgr.import_invoice(xml_saved_path)
                                invoices_count += 1
                            except Exception as err:
                                logger.error(f"[Sync] Errore parsing XML {xml_saved_path}: {err}")
                        elif not exists_p:
                            tot = float(pinv.get("fxml_tot") or pinv.get("fxml_imp") or pinv.get("xml_tot_doc") or 0.0)
                            new_p = Invoice(
                                supplier_id=supp.id,
                                number=num,
                                date=dt,
                                total_amount=tot,
                                file_path=file_name
                            )
                            session.add(new_p)
                            invoices_count += 1

            session.commit()
            status_rec.status = "SUCCESS"
            status_rec.last_sync_time = datetime.utcnow()
            status_rec.items_synced = invoices_count
            session.commit()
        except Exception as e:
            session.rollback()
            status_rec.status = "ERROR"
            status_rec.last_error = str(e)
            session.commit()
            logger.error(f"[Sync] Errore sincronizzazione fatture: {e}")

        return {"invoices_count": invoices_count}


class BackgroundSyncThread(QThread):
    """Thread di esecuzione sincronizzazione asincrono per non bloccare l'interfaccia utente."""
    sync_finished = pyqtSignal(dict)

    def __init__(self, force: bool = False, parent=None):
        super().__init__(parent)
        self.force = force
        self.engine = BKodeSyncEngine()

    def run(self):
        result = self.engine.sync_all(force=self.force)
        self.sync_finished.emit(result)


class BackgroundSyncManager(QObject):
    """Gestore del timer periodico integrato nella finestra principale del gestionale."""
    status_updated = pyqtSignal(str)

    def __init__(self, interval_minutes: int = 15, parent=None):
        super().__init__(parent)
        self.interval_minutes = interval_minutes
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.trigger_sync)
        self.current_thread: Optional[BackgroundSyncThread] = None

    def start(self):
        """Avvia il monitoraggio periodico in background."""
        logger.info(f"[SyncManager] Avviato timer sincronizzazione ogni {self.interval_minutes} minuti.")
        # Esegui un primo controllo dopo 5 secondi dall'avvio
        QTimer.singleShot(5000, self.trigger_sync)
        self.timer.start(self.interval_minutes * 60 * 1000)

    def stop(self):
        """Ferma il timer."""
        self.timer.stop()

    def trigger_sync(self, force: bool = False):
        """Avvia la sincronizzazione asincrona se non già in esecuzione."""
        if self.current_thread and self.current_thread.isRunning():
            logger.info("[SyncManager] Sincronizzazione già in corso su questo processo. Ignoro richiesta.")
            return

        self.current_thread = BackgroundSyncThread(force=force, parent=self)
        self.current_thread.sync_finished.connect(self._on_sync_finished)
        self.current_thread.start()

    def _on_sync_finished(self, summary: dict):
        if summary.get("executed"):
            msg = f"Sincronizzazione B-Kode completata ({summary.get('price_items_synced', 0)} listini, {summary.get('products_synced', 0)} nuovi articoli)."
            self.status_updated.emit(msg)
        elif summary.get("reason"):
            self.status_updated.emit(summary["reason"])
