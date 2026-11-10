from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QGroupBox, QFormLayout, QMessageBox, QApplication, QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from app.utils.ui_utils import SortableTableWidgetItem

class ProductLinkDialog(QDialog):
    """Finestra di dialogo per collegare un articolo/codice fornitore a un articolo del catalogo master Angeleri."""

    def __init__(self, controller, supplier_id: int, supplier_name: str, 
                 supplier_code: str, supplier_desc: str = "", current_product_id: int = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self.supplier_code = (supplier_code or "").strip()
        self.supplier_desc = supplier_desc or ""
        self.current_product_id = current_product_id
        self.selected_product_id = None
        self.selected_product_code = None

        self.setWindowTitle("🔗 Collega Articolo Fornitore a Codice Interno Angeleri")
        self.resize(850, 560)
        self.setup_ui()
        self.load_master_products()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # ── 1. Box Info Articolo Fornitore ──
        box_forn = QGroupBox("Dettagli Articolo Fornitore da Collegare")
        box_forn.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #CBD5E1; 
                border-radius: 6px; 
                margin-top: 6px; 
                padding-top: 10px;
                background-color: #F8FAFC;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        form_info = QFormLayout(box_forn)
        form_info.setSpacing(6)

        lbl_supp = QLabel(self.supplier_name)
        lbl_supp.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        form_info.addRow("Fornitore:", lbl_supp)

        lbl_code = QLabel(self.supplier_code or "Non specificato")
        lbl_code.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        lbl_code.setStyleSheet("color: #0284C7;")
        form_info.addRow("Codice Fornitore:", lbl_code)

        lbl_desc = QLabel(self.supplier_desc or "-")
        lbl_desc.setStyleSheet("color: #334155;")
        form_info.addRow("Descrizione:", lbl_desc)

        layout.addWidget(box_forn)

        # ── 2. Barra di Ricerca Catalogo Interno ──
        search_box = QHBoxLayout()
        search_lbl = QLabel("🔍 Cerca Articolo Master:")
        search_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        search_box.addWidget(search_lbl)

        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(34)
        self.search_input.setPlaceholderText("Digita codice master (es. L040-0086), descrizione o categoria...")
        # Precompila con una ricerca sensata
        suggested = self.supplier_code.replace("--", "-").strip(" -")
        if len(suggested) >= 3:
            self.search_input.setText(suggested)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self.load_master_products)
        search_box.addWidget(self.search_input, stretch=1)

        btn_search = QPushButton("Cerca")
        btn_search.setFixedHeight(34)
        btn_search.setStyleSheet("padding: 0 16px; font-weight: bold;")
        btn_search.clicked.connect(self.load_master_products)
        search_box.addWidget(btn_search)

        layout.addLayout(search_box)

        # ── 3. Tabella Articoli Catalogo Master Angeleri ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Codice Master", "Descrizione Articolo", "Categoria", 
            "N. Disegno", "Costo STD", "Listino Vendita"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table, stretch=1)

        # ── 4. Footer con Conteggio, Opzione B-Kode e Azioni ──
        footer = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #64748B; font-size: 11px;")
        footer.addWidget(self.lbl_count, stretch=1)

        self.chk_sync_bkode = QCheckBox("☁️ Salva e aggiorna anche su B-Kode Cloud (mgafoForm)")
        self.chk_sync_bkode.setChecked(True)
        self.chk_sync_bkode.setStyleSheet("font-weight: bold; color: #0369A1; font-size: 11px;")
        self.chk_sync_bkode.setToolTip("Se selezionato, scrive l'associazione direttamente nella scheda 'Articoli Fornitori' di B-Kode Cloud.")
        footer.addWidget(self.chk_sync_bkode)

        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        self.btn_confirm = QPushButton("🔗 Collega e Salva")
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: white;
                font-weight: bold;
                padding: 0 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:disabled { background-color: #94A3B8; }
        """)
        self.btn_confirm.clicked.connect(self.save_link)
        footer.addWidget(self.btn_confirm)

        layout.addLayout(footer)

    def _on_search_text_changed(self):
        # Ricerca dinamica con ricaricamento
        self.load_master_products()

    def load_master_products(self):
        query = self.search_input.text().strip()
        from app.database import get_db_session, Product
        from sqlalchemy import or_

        session = get_db_session()
        try:
            q = session.query(Product)
            if query:
                words = query.split()
                from sqlalchemy import and_
                conds = []
                for w in words:
                    pat = f"%{w}%"
                    conds.append(or_(
                        Product.code.ilike(pat),
                        Product.name.ilike(pat),
                        Product.category.ilike(pat),
                        Product.drawing_number.ilike(pat)
                    ))
                q = q.filter(and_(*conds))

            total_found = q.count()
            products = q.order_by(Product.code).limit(200).all()

            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(products))

            selected_row = -1
            for i, p in enumerate(products):
                item_code = SortableTableWidgetItem(p.code)
                item_code.setData(Qt.ItemDataRole.UserRole, p.id)
                self.table.setItem(i, 0, item_code)

                self.table.setItem(i, 1, QTableWidgetItem(p.name or "-"))
                self.table.setItem(i, 2, QTableWidgetItem(p.category or "-"))
                self.table.setItem(i, 3, QTableWidgetItem(p.drawing_number or "-"))

                cost_val = float(p.production_cost or 0.0)
                cost_str = f"€ {cost_val:,.2f}" if cost_val else "-"
                self.table.setItem(i, 4, SortableTableWidgetItem(cost_str, sort_value=cost_val))

                price_val = float(p.list_price or 0.0)
                price_str = f"€ {price_val:,.2f}" if price_val else "-"
                self.table.setItem(i, 5, SortableTableWidgetItem(price_str, sort_value=price_val))

                if self.current_product_id and p.id == self.current_product_id:
                    selected_row = i

            self.table.setSortingEnabled(True)

            if len(products) < total_found:
                self.lbl_count.setText(f"Trovati {len(products)} di {total_found} articoli (limite visualizzazione rapida 200).")
            else:
                self.lbl_count.setText(f"Trovati {len(products)} articoli.")

            if selected_row >= 0:
                self.table.selectRow(selected_row)
            elif len(products) > 0 and len(query) >= 3:
                self.table.selectRow(0)

        except Exception as e:
            self.lbl_count.setText(f"Errore ricerca: {e}")
        finally:
            session.close()

    def _on_selection_changed(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                self.selected_product_id = item.data(Qt.ItemDataRole.UserRole)
                self.selected_product_code = item.text().strip()
                self.btn_confirm.setEnabled(True)
                return
        self.selected_product_id = None
        self.selected_product_code = None
        self.btn_confirm.setEnabled(False)

    def _on_cell_double_clicked(self, row, col):
        self._on_selection_changed()
        if self.selected_product_id:
            self.save_link()

    def save_link(self):
        if not self.selected_product_id:
            return

        # Verifica stato B-Kode
        sync_bkode = self.chk_sync_bkode.isChecked()
        bkode_msg = "\n• Aggiornamento scheda 'Articoli Fornitori' su B-Kode Cloud: ATTIVO" if sync_bkode else ""

        reply = QMessageBox.question(
            self,
            "Conferma Associazione Articolo",
            f"Vuoi associare l'articolo del fornitore:\n\n"
            f"• Codice Fornitore: {self.supplier_code}\n"
            f"• Fornitore: {self.supplier_name}\n\n"
            f"al Codice Interno Angeleri:\n"
            f"• {self.selected_product_code} ?\n\n"
            f"Operazioni pianificate:\n"
            f"• Salvataggio associazione nel database locale\n"
            f"• Collegamento automatico a tutte le fatture storiche e future{bkode_msg}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = self.controller.link_supplier_item_to_product(
                supplier_id=self.supplier_id,
                supplier_code=self.supplier_code,
                product_id=self.selected_product_id,
                supplier_description=self.supplier_desc,
                sync_to_bkode=sync_bkode
            )
            if res.get("success"):
                inv_count = res.get("updated_items", 0)
                bkode_res = res.get("bkode_result")
                
                detail_lines = [f"Articolo '{self.supplier_code}' associato a '{self.selected_product_code}'."]
                if inv_count > 0:
                    detail_lines.append(f"• Aggiornate {inv_count} righe nelle fatture di questo fornitore.")
                
                if sync_bkode:
                    if bkode_res and bkode_res.get("success"):
                        detail_lines.append(f"• ☁️ Registrato su B-Kode Cloud con successo (ID B-Kode: {bkode_res.get('id', 'OK')}).")
                    elif bkode_res:
                        detail_lines.append(f"• ⚠️ B-Kode Cloud: {bkode_res.get('message', 'Non sincronizzato')}")

                QMessageBox.information(
                    self,
                    "Associazione Completata",
                    "\n".join(detail_lines)
                )
                self.accept()
            else:
                QMessageBox.warning(self, "Errore", f"Impossibile completare l'associazione:\n{res.get('message', 'Dati non validi.')}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante il salvataggio: {e}")
        finally:
            QApplication.restoreOverrideCursor()
