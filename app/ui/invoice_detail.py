import os
import json
import logging
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGroupBox, QGridLayout, QMessageBox,
    QApplication, QFrame
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from app.utils.ui_utils import SortableTableWidgetItem
from app.database import (
    get_db_session, Invoice, InvoiceItem, Supplier,
    SalesInvoice, SalesInvoiceItem, Customer
)

logger = logging.getLogger(__name__)


def resolve_invoice_file_path(file_path: str) -> str | None:
    """Risolve il percorso assoluto del file sorgente della fattura sul file system o sul NAS."""
    if not file_path:
        return None
    clean = file_path.strip().replace('/', '\\')
    if os.path.isabs(clean) and os.path.exists(clean):
        return clean

    base_nas_fornitori = r"\\angeleri_new\Pubblica\Database\Fornitori"
    base_nas_clienti = r"\\angeleri_new\Pubblica\Database\File_per_progetto\Fatture_Clienti"
    fname = os.path.basename(clean)

    candidates = [
        clean,
        os.path.join(base_nas_fornitori, clean),
        os.path.join(base_nas_fornitori, fname),
        os.path.join(base_nas_clienti, fname),
        os.path.join(r"\\angeleri_new\Pubblica\Database\File_per_progetto", fname),
        os.path.join(os.getcwd(), clean),
        os.path.join(os.getcwd(), "File_per_progetto", "Fatture_Clienti", fname),
        os.path.join(os.getcwd(), "File_per_progetto", fname),
        os.path.join(os.getcwd(), "Fornitori", clean),
        os.path.join(os.getcwd(), "data", "Fornitori", clean),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    # Ricerca rapida nelle sottocartelle fornitori sul NAS se è un file XML o PDF
    if os.path.exists(base_nas_fornitori) and fname.lower().endswith(('.xml', '.pdf', '.p7m')):
        try:
            for entry in os.scandir(base_nas_fornitori):
                if entry.is_dir():
                    sub_cand = os.path.join(entry.path, fname)
                    if os.path.exists(sub_cand):
                        return os.path.abspath(sub_cand)
        except Exception:
            pass

    return None


class InvoiceDetailDialog(QWidget):
    """
    Visualizzatore completo e universale per fatture:
    supporta sia fatture di vendita ai clienti (SalesInvoice) che d'acquisto dai fornitori (Invoice).
    Implementato come QWidget (non QDialog) per evitare interferenze con il focus delle altre finestre.
    """

    def __init__(self, invoice_id: int = None, invoice_type: str = "auto",
                 invoice_number: str = None, invoice_year: int = None, parent=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.invoice_type = invoice_type.lower() if invoice_type else "auto"
        self.invoice_number = str(invoice_number).strip() if invoice_number is not None else None
        self.invoice_year = int(invoice_year) if invoice_year else None

        self.file_path = None
        self.resolved_file_path = None
        self.summary_text = ""

        self.setWindowTitle("Dettaglio Completo Fattura")
        self.resize(1000, 620)
        # Window: finestra indipendente senza parent behavior
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setup_ui()
        self.load_data()


    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # ── Testata Documento ──
        self.grp_header = QGroupBox("Dettagli Testata Fattura")
        self.grp_header.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                margin-top: 6px;
                padding-top: 10px;
                background-color: #F8FAFC;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1E293B;
            }
        """)
        grid = QGridLayout(self.grp_header)
        grid.setSpacing(8)

        # Badge Tipo Documento
        self.lbl_badge = QLabel("-")
        self.lbl_badge.setStyleSheet("""
            padding: 4px 10px;
            font-weight: bold;
            font-size: 12px;
            border-radius: 4px;
            color: white;
            background-color: #0284C7;
        """)
        self.lbl_badge.setFixedWidth(230)
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.lbl_badge, 0, 0, 1, 1)

        # Numero e Data
        self.lbl_num_data = QLabel("-")
        self.lbl_num_data.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_num_data.setStyleSheet("color: #0F172A;")
        grid.addWidget(self.lbl_num_data, 0, 1, 1, 2)

        # Soggetto (Cliente o Fornitore)
        lbl_sogg_title = QLabel("Intestatario:")
        lbl_sogg_title.setStyleSheet("color: #64748B; font-weight: bold;")
        self.lbl_soggetto = QLabel("-")
        self.lbl_soggetto.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_soggetto.setStyleSheet("color: #1E3A8A;")
        grid.addWidget(lbl_sogg_title, 1, 0)
        grid.addWidget(self.lbl_soggetto, 1, 1, 1, 2)

        # P.IVA e Sede
        self.lbl_piva = QLabel("-")
        self.lbl_piva.setStyleSheet("color: #475569; font-size: 12px;")
        grid.addWidget(self.lbl_piva, 2, 0, 1, 3)

        # Box Totale a destra
        tot_box = QVBoxLayout()
        self.lbl_imponibile = QLabel("Imponibile: -")
        self.lbl_imponibile.setStyleSheet("color: #64748B; font-size: 12px;")
        self.lbl_totale = QLabel("Totale: € 0,00")
        self.lbl_totale.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.lbl_totale.setStyleSheet("color: #166534;")

        tot_box.addWidget(self.lbl_imponibile)
        tot_box.addWidget(self.lbl_totale)
        grid.addLayout(tot_box, 0, 3, 3, 1)

        layout.addWidget(self.grp_header)

        # ── Tabella Righe Articolo ──
        lbl_righe = QLabel("Righe Articolo del Documento")
        lbl_righe.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        lbl_righe.setStyleSheet("color: #334155; margin-top: 4px;")
        layout.addWidget(lbl_righe)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Riga", "Cod. Articolo", "Descrizione", "Q.tà", "U.M.", "Prezzo Unit.", "Sconto %", "Totale Riga"
        ])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                gridline-color: #E2E8F0;
                background-color: #FFFFFF;
                alternate-background-color: #F8FAFC;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #1E293B;
                font-weight: bold;
                border: 1px solid #E2E8F0;
                padding: 5px;
            }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table, stretch=1)

        # ── Footer / Azioni ──
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #64748B; font-size: 11px;")
        footer.addWidget(self.lbl_count, stretch=1)

        self.btn_open_file = QPushButton("📄 Apri File Originale (PDF / XML)")
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.setStyleSheet("""
            QPushButton {
                background-color: #E65100;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        self.btn_open_file.clicked.connect(self.open_original_file)
        footer.addWidget(self.btn_open_file)

        btn_copy = QPushButton("📋 Copia Dati")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #334155;
                border: 1px solid #CBD5E1;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        btn_copy.clicked.connect(self.copy_summary_to_clipboard)
        footer.addWidget(btn_copy)

        btn_tile = QPushButton("🪟 Affianca a Destra")
        btn_tile.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tile.setToolTip("Posiziona questa fattura sulla metà destra dello schermo e il gestionale sulla metà sinistra, per consultare entrambi contemporaneamente.")
        btn_tile.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #0284C7;
                border: 1px solid #CBD5E1;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #E0F2FE; }
        """)
        btn_tile.clicked.connect(self.tile_side_by_side)
        footer.addWidget(btn_tile)

        btn_close = QPushButton("Chiudi")
        btn_close.setFixedWidth(90)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #64748B;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)

        layout.addLayout(footer)

    def tile_side_by_side(self):
        """Affianca questa finestra sul lato destro dello schermo e la finestra principale sul lato sinistro."""
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().availableGeometry()
        mid_x = screen.x() + screen.width() // 2
        half_w = screen.width() // 2
        h = screen.height()
        
        self.setGeometry(mid_x, screen.y(), half_w, h)
        if self.parent():
            try:
                self.parent().showNormal()
                self.parent().setGeometry(screen.x(), screen.y(), half_w, h)
                self.parent().raise_()
                self.parent().activateWindow()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

    def closeEvent(self, event):
        if self.parent():
            try:
                self.parent().raise_()
                self.parent().activateWindow()
            except Exception:
                pass
        super().closeEvent(event)

    def load_data(self):
        session = get_db_session()
        try:
            inv_sale = None
            inv_purchase = None

            # 1. Risoluzione Fattura Vendita (SalesInvoice)
            if self.invoice_type in ("sale", "sales", "vendita", "auto"):
                if self.invoice_id and self.invoice_type != "purchase":
                    inv_sale = session.get(SalesInvoice, self.invoice_id)
                elif self.invoice_number:
                    q = session.query(SalesInvoice).filter(SalesInvoice.number == self.invoice_number)
                    if self.invoice_year:
                        q = q.filter(SalesInvoice.year == self.invoice_year)
                    inv_sale = q.order_by(SalesInvoice.date.desc()).first()

            # 2. Risoluzione Fattura Acquisto (Invoice)
            if not inv_sale and self.invoice_type in ("purchase", "acquisto", "fornitore", "auto"):
                if self.invoice_id:
                    inv_purchase = session.get(Invoice, self.invoice_id)
                elif self.invoice_number:
                    inv_purchase = session.query(Invoice).filter(Invoice.number == self.invoice_number).order_by(Invoice.date.desc()).first()

            if inv_sale:
                self._populate_sales_invoice(inv_sale)
            elif inv_purchase:
                if len(inv_purchase.items) == 0:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    try:
                        inv_purchase = self._auto_recover_purchase_items(session, inv_purchase)
                    finally:
                        QApplication.restoreOverrideCursor()
                self._populate_purchase_invoice(inv_purchase)
            else:
                self.setWindowTitle("Fattura Non Trovata")
                self.lbl_num_data.setText("⚠️ Fattura non trovata nell'archivio.")
                self.lbl_badge.setText("DOCUMENTO NON TROVATO")
                self.lbl_badge.setStyleSheet("background-color: #DC2626; color: white; padding: 4px;")
                self.btn_open_file.setEnabled(False)
        except Exception as e:
            self.lbl_num_data.setText(f"Errore caricamento: {e}")
        finally:
            session.close()

    def _populate_sales_invoice(self, inv: SalesInvoice):
        self.file_path = inv.file_path
        self.resolved_file_path = resolve_invoice_file_path(inv.file_path)

        date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
        self.setWindowTitle(f"Fattura Vendita n. {inv.number}/{inv.year} — {inv.customer.name if inv.customer else 'Cliente'}")

        self.lbl_badge.setText("🟢 FATTURA DI VENDITA CLIENTE")
        self.lbl_badge.setStyleSheet("background-color: #15803D; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")

        doc_type = inv.doc_type or "Fattura"
        self.lbl_num_data.setText(f"N. {inv.number}/{inv.year} ({doc_type})  •  Data: {date_str}")
        self.lbl_soggetto.setText(inv.customer.name if inv.customer else "Cliente Sconosciuto")

        piva_str = f"P.IVA / CF: {inv.customer.piva_cf}" if inv.customer and inv.customer.piva_cf else "P.IVA: Non specificata"
        addr_str = f"Sede: {inv.customer.address or ''} ({inv.customer.country or 'IT'})" if inv.customer else ""
        self.lbl_piva.setText(f"{piva_str}   |   {addr_str}")

        tot_net = sum(it.total_price or 0.0 for it in inv.items)
        self.lbl_imponibile.setText(f"Imponibile Netto: € {tot_net:,.2f}")
        self.lbl_totale.setText(f"Totale Fattura: € {inv.total_amount:,.2f}")

        # Popola tabella righe
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(inv.items))

        summary_lines = [
            f"FATTURA DI VENDITA N. {inv.number}/{inv.year} del {date_str}",
            f"Cliente: {inv.customer.name if inv.customer else '-'}",
            f"Totale: € {inv.total_amount:,.2f}",
            "--- RIGHE ARTICOLO ---"
        ]

        for i, it in enumerate(inv.items):
            riga_num = it.line_number or (i + 1)
            # Riga
            item_r = SortableTableWidgetItem(str(riga_num), sort_value=riga_num)
            item_r.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, item_r)

            # Codice Articolo
            code_str = it.raw_code or (it.product.code if it.product else "-")
            self.table.setItem(i, 1, QTableWidgetItem(code_str))

            # Descrizione
            self.table.setItem(i, 2, QTableWidgetItem(it.description or "-"))

            # Quantità
            qty = it.quantity or 0.0
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:,.2f}".rstrip('0').rstrip('.')
            item_q = SortableTableWidgetItem(qty_str, sort_value=qty)
            item_q.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 3, item_q)

            # U.M.
            item_um = QTableWidgetItem(it.unit_measure or "NR")
            item_um.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 4, item_um)

            # Prezzo Unitario
            pr = it.unit_price or 0.0
            item_p = SortableTableWidgetItem(f"€ {pr:,.2f}", sort_value=pr)
            item_p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 5, item_p)

            # Sconto
            sc = it.discount or 0.0
            item_sc = SortableTableWidgetItem(f"{sc:.1f}%" if sc else "-", sort_value=sc)
            item_sc.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 6, item_sc)

            # Totale Riga Netto
            tot_r = it.total_price or 0.0
            item_tot = SortableTableWidgetItem(f"€ {tot_r:,.2f}", sort_value=tot_r)
            item_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 7, item_tot)

            summary_lines.append(f"- [{code_str}] {it.description} | Qta: {qty} | Prezzo: € {pr:,.2f} | Totale: € {tot_r:,.2f}")

        self.table.setSortingEnabled(True)
        self.summary_text = "\n".join(summary_lines)

        file_status = f"Disponibile ({os.path.basename(self.resolved_file_path)})" if self.resolved_file_path else (self.file_path or "N/D")
        self.lbl_count.setText(f"{len(inv.items)} righe articolo  •  File sorgente: {file_status}")
        self.btn_open_file.setEnabled(bool(self.resolved_file_path))

    def _auto_recover_purchase_items(self, session, inv: Invoice) -> Invoice:
        """
        Recupera on-demand gli articoli della fattura se assenti a DB.
        1. Se esiste già un'altra fattura nel DB associata allo stesso file XML
           o allo stesso numero/data che ha gli articoli (es. generata con nome fornitore canonico
           anziché '[CODIFICARE] Nome'), aggancia quella ed elimina il duplicato vuoto.
        2. Altrimenti verifica se l'XML è già presente sul NAS; se non trovato,
           interroga B-Kode Cloud, scarica l'XML originale, lo archivia sul NAS
           e popola le righe articolo tramite InvoiceManager.
        """
        fname = os.path.basename(inv.file_path) if inv.file_path else ""

        # Controllo 1: Esiste già un'altra fattura popolata con lo stesso file o numero/data?
        other = None
        if fname:
            other = session.query(Invoice).filter(
                Invoice.id != inv.id,
                Invoice.file_path.ilike(f"%{fname}%"),
                Invoice.items.any()
            ).first()
        if not other and inv.number and inv.date:
            other = session.query(Invoice).filter(
                Invoice.id != inv.id,
                Invoice.number == str(inv.number).strip(),
                Invoice.date == inv.date,
                Invoice.items.any()
            ).first()

        if other and len(other.items) > 0:
            logger.info(f"[InvoiceDetail] Trovata fattura gemella ID={other.id} con {len(other.items)} articoli. Rimuovo duplicato vuoto ID={inv.id}.")
            try:
                session.delete(inv)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"[InvoiceDetail] Impossibile eliminare duplicato vuoto ID={inv.id}: {e}")
            return other

        xml_target_path = resolve_invoice_file_path(inv.file_path)

        # Se non è su disco, tentiamo il download trasparente da B-Kode Cloud
        if not xml_target_path or not os.path.exists(xml_target_path):
            try:
                from app.utils.bkode_client import BKodeClient
                client = BKodeClient()
                if client.ensure_authenticated():
                    file_name = fname
                    bkode_item = None

                    # Ricerca su B-Kode per nome file se disponibile
                    if file_name and file_name.lower().endswith(('.xml', '.p7m')):
                        res = client._post_grid('fatforxmlList', {
                            'filter': json.dumps([{'field': 'fxml_file', 'data': {'type': 'string', 'value': file_name}}]),
                            'start': '0', 'limit': '5'
                        })
                        items = res.get('items', []) if res else []
                        if items:
                            bkode_item = items[0]

                    # Ricerca su B-Kode per numero fattura se non trovato per file
                    if not bkode_item and inv.number:
                        res = client._post_grid('fatforxmlList', {
                            'filter': json.dumps([{'field': 'fxml_nr_fat', 'data': {'type': 'string', 'value': str(inv.number)}}]),
                            'start': '0', 'limit': '15'
                        })
                        items = res.get('items', []) if res else []
                        for it in items:
                            dt_str = it.get('fxml_dt_fat') or ''
                            if inv.date and dt_str.startswith(str(inv.date)[:4]):
                                bkode_item = it
                                break
                        if not bkode_item and items:
                            bkode_item = items[0]

                    if bkode_item:
                        fid = bkode_item.get('fxml_id')
                        fn = bkode_item.get('fxml_file') or file_name or f"fattura_{inv.number}.xml"
                        xml_bytes = client.download_purchase_invoice_xml(fid, fn)
                        if xml_bytes:
                            supp_name = inv.supplier.name if inv.supplier else "Altri_Fornitori"
                            from app.controllers.invoice_manager import InvoiceManager
                            safe_name = InvoiceManager._normalize_supplier(supp_name)
                            safe_name = safe_name.replace("SRL", "").replace("S.P.A.", "").replace("S.R.L.", "").replace("SPA", "").strip() or "Varie"

                            base_nas = r"\\angeleri_new\Pubblica\Database\Fornitori"
                            target_dir = os.path.join(base_nas, safe_name) if os.path.exists(base_nas) else os.path.join(os.getcwd(), "data", "Fornitori", safe_name)
                            try:
                                os.makedirs(target_dir, exist_ok=True)
                            except Exception:
                                pass
                            dest_path = os.path.join(target_dir, fn)
                            with open(dest_path, "wb") as f:
                                f.write(xml_bytes)
                            xml_target_path = dest_path
            except Exception as e:
                logger.warning(f"[InvoiceDetail] Errore durante il recupero automatico da B-Kode: {e}")

        # Se abbiamo il file XML (trovato o appena scaricato), effettuiamo l'importazione
        if xml_target_path and os.path.exists(xml_target_path):
            try:
                from app.controllers.invoice_manager import InvoiceManager
                mgr = InvoiceManager()
                try:
                    mgr.import_invoice(xml_target_path)
                finally:
                    try:
                        mgr.session.close()
                    except Exception:
                        pass

                # Aggiorna il percorso file nella fattura corrente
                inv.file_path = xml_target_path
                session.commit()
                session.expire(inv)

                # Se dopo l'importazione inv ha articoli, perfetto!
                if len(inv.items) > 0:
                    logger.info(f"[InvoiceDetail] Auto-recupero completato per fattura ID={inv.id} n. {inv.number} ({len(inv.items)} articoli)")
                    return inv

                # Se inv ha ancora 0 articoli, verifica se l'importazione ha creato/aggiornato una fattura con nome canonico
                if fname:
                    other = session.query(Invoice).filter(
                        Invoice.id != inv.id,
                        Invoice.file_path.ilike(f"%{fname}%"),
                        Invoice.items.any()
                    ).first()
                    if other and len(other.items) > 0:
                        logger.info(f"[InvoiceDetail] Dopo import, trovata fattura canonica ID={other.id} con {len(other.items)} articoli. Rimuovo duplicato vuoto ID={inv.id}.")
                        try:
                            session.delete(inv)
                            session.commit()
                        except Exception:
                            session.rollback()
                        return other

            except Exception as e:
                logger.error(f"[InvoiceDetail] Errore durante l'importazione automatica delle righe: {e}")

        return inv

    def _populate_purchase_invoice(self, inv: Invoice):
        self.file_path = inv.file_path
        self.resolved_file_path = resolve_invoice_file_path(inv.file_path)

        date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
        self.setWindowTitle(f"Fattura Acquisto n. {inv.number} — {inv.supplier.name if inv.supplier else 'Fornitore'}")

        self.lbl_badge.setText("🔵 FATTURA ACQUISTO FORNITORE")
        self.lbl_badge.setStyleSheet("background-color: #1E40AF; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")

        self.lbl_num_data.setText(f"N. {inv.number}  •  Data: {date_str}")
        self.lbl_soggetto.setText(inv.supplier.name if inv.supplier else "Fornitore Sconosciuto")

        piva_str = f"P.IVA: {inv.supplier.piva}" if inv.supplier and inv.supplier.piva else "P.IVA: Non specificata"
        self.lbl_piva.setText(piva_str)

        tot_net = sum(it.total_price or 0.0 for it in inv.items)
        self.lbl_imponibile.setText(f"Imponibile Netto: € {tot_net:,.2f}")
        self.lbl_totale.setText(f"Totale Fattura: € {inv.total_amount:,.2f}")

        # Popola tabella righe
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(inv.items))

        summary_lines = [
            f"FATTURA ACQUISTO N. {inv.number} del {date_str}",
            f"Fornitore: {inv.supplier.name if inv.supplier else '-'}",
            f"Totale: € {inv.total_amount:,.2f}",
            "--- RIGHE ARTICOLO ---"
        ]

        for i, it in enumerate(inv.items):
            riga_num = i + 1
            item_r = SortableTableWidgetItem(str(riga_num), sort_value=riga_num)
            item_r.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, item_r)

            code_str = it.code or (it.customer_code or "-")
            self.table.setItem(i, 1, QTableWidgetItem(code_str))
            self.table.setItem(i, 2, QTableWidgetItem(it.description or "-"))

            qty = it.quantity or 0.0
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:,.2f}".rstrip('0').rstrip('.')
            item_q = SortableTableWidgetItem(qty_str, sort_value=qty)
            item_q.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 3, item_q)

            item_um = QTableWidgetItem("NR")
            item_um.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 4, item_um)

            pr = it.unit_price or 0.0
            item_p = SortableTableWidgetItem(f"€ {pr:,.4f}", sort_value=pr)
            item_p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 5, item_p)

            item_sc = QTableWidgetItem("-")
            item_sc.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 6, item_sc)

            tot_r = it.total_price or 0.0
            item_tot = SortableTableWidgetItem(f"€ {tot_r:,.2f}", sort_value=tot_r)
            item_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 7, item_tot)

            summary_lines.append(f"- [{code_str}] {it.description} | Qta: {qty} | Prezzo: € {pr:,.4f} | Totale: € {tot_r:,.2f}")

        self.table.setSortingEnabled(True)
        self.summary_text = "\n".join(summary_lines)

        file_status = f"Disponibile ({os.path.basename(self.resolved_file_path)})" if self.resolved_file_path else (self.file_path or "N/D")
        self.lbl_count.setText(f"{len(inv.items)} righe articolo  •  File sorgente: {file_status}")
        self.btn_open_file.setEnabled(bool(self.resolved_file_path))

    def open_original_file(self):
        """Apre il file originale (PDF o XML) con l'applicazione di sistema di Windows."""
        if not self.resolved_file_path or not os.path.exists(self.resolved_file_path):
            QMessageBox.information(
                self, "File non trovato",
                f"Il file sorgente collegato alla fattura non è stato trovato sul disco:\n{self.file_path or 'Percorso non specificato'}"
            )
            return

        try:
            os.startfile(self.resolved_file_path)
        except Exception as e:
            QMessageBox.warning(self, "Errore Apertura File", f"Impossibile aprire il file:\n{e}")

    def copy_summary_to_clipboard(self):
        """Copia il testo riassuntivo della fattura negli appunti."""
        if self.summary_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.summary_text)
            QMessageBox.information(self, "Copiato", "Riepilogo e righe fattura copiati negli appunti!")
