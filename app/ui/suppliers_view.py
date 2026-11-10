from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QSplitter, QTabWidget, QGroupBox, QFormLayout, 
                             QComboBox, QCheckBox, QMenu, QMessageBox, QApplication)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QAction, QColor, QBrush
from app.utils.ui_utils import SortableTableWidgetItem
from app.ui.product_link_dialog import ProductLinkDialog

class SuppliersWidget(QWidget):
    """Scheda Anagrafica Fornitori con ricerca articoli in fattura (singolo fornitore o globale) e associazione catalogo interno."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.current_supplier_id = None
        self.current_supplier_name = ""
        self.setup_ui()
        self.load_suppliers()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # ── Top Bar Principale ──
        top_layout = QHBoxLayout()
        title = QLabel("🏭 Anagrafica Fornitori")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch()

        # Filtro Tipologia
        top_layout.addWidget(QLabel("Visualizza:"))
        self.combo_filter = QComboBox()
        self.combo_filter.setFixedHeight(36)
        self.combo_filter.addItem("Tutti i fornitori", "all")
        self.combo_filter.addItem("Solo con fatture d'acquisto", "invoices_only")
        self.combo_filter.addItem("Solo con articoli a catalogo", "catalog_only")
        self.combo_filter.currentIndexChanged.connect(self.load_suppliers)
        top_layout.addWidget(self.combo_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca fornitore per nome o P.IVA...")
        self.search_input.setFixedWidth(280)
        self.search_input.setFixedHeight(36)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.load_suppliers)
        self.search_input.textChanged.connect(self._search_timer.start)
        top_layout.addWidget(self.search_input)

        btn_refresh = QPushButton("🔄 Aggiorna")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self.load_suppliers)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── PANNELLO SINISTRO: Tabella Elenco Fornitori ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table_suppliers = QTableWidget()
        self.table_suppliers.setColumnCount(6)
        self.table_suppliers.setHorizontalHeaderLabels([
            "Fornitore / Ragione Sociale", "P.IVA", "Fatture", "Articoli a Catalogo", "Spesa Totale Netta", "Ultima Fattura"
        ])
        h_supp = self.table_suppliers.horizontalHeader()
        h_supp.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_supp.setStretchLastSection(True)
        self.table_suppliers.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_suppliers.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_suppliers.setSortingEnabled(True)
        self.table_suppliers.itemSelectionChanged.connect(self.on_supplier_selected)
        left_layout.addWidget(self.table_suppliers)

        self.lbl_count = QLabel("Caricamento fornitori...")
        self.lbl_count.setStyleSheet("color: #64748B; font-size: 12px;")
        left_layout.addWidget(self.lbl_count)
        splitter.addWidget(left_panel)

        # ── PANNELLO DESTRO: Scheda Dettaglio Fornitore & Ricerche ──
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Intestazione Scheda
        self.box_info = QGroupBox("Scheda Dettaglio Fornitore")
        self.box_info.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        info_layout = QFormLayout(self.box_info)

        self.lbl_name = QLabel("-")
        self.lbl_name.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_piva = QLabel("-")
        self.lbl_totals = QLabel("-")
        self.lbl_totals.setStyleSheet("color: #C62828; font-weight: bold; font-size: 13px;")

        info_layout.addRow("Fornitore:", self.lbl_name)
        info_layout.addRow("P.IVA:", self.lbl_piva)
        info_layout.addRow("Riepilogo Spese:", self.lbl_totals)

        right_layout.addWidget(self.box_info)

        # Tabs Scheda Fornitore
        self.supp_tabs = QTabWidget()

        # ════════════════════════════════════════════════════════
        # TAB 1: RICERCA ARTICOLI IN FATTURA (SPECIFICA O GLOBALE)
        # ════════════════════════════════════════════════════════
        tab_items_widget = QWidget()
        tab_items_layout = QVBoxLayout(tab_items_widget)
        tab_items_layout.setContentsMargins(5, 8, 5, 5)
        tab_items_layout.setSpacing(6)

        # Barra di ricerca interna alle fatture
        bar_search_items = QHBoxLayout()
        self.txt_item_search = QLineEdit()
        self.txt_item_search.setFixedHeight(34)
        self.txt_item_search.setPlaceholderText("Cerca codice articolo, descrizione o numero fattura...")
        self.txt_item_search.returnPressed.connect(self.search_invoice_items)
        bar_search_items.addWidget(self.txt_item_search, stretch=1)

        self.chk_global_search = QCheckBox("🌐 Cerca su TUTTI i fornitori (Globale)")
        self.chk_global_search.setToolTip("Se selezionato, cerca gli articoli tra le fatture di qualsiasi fornitore; altrimenti solo per il fornitore selezionato.")
        self.chk_global_search.setStyleSheet("font-weight: bold; color: #0369A1;")
        self.chk_global_search.stateChanged.connect(self._on_global_checkbox_changed)
        bar_search_items.addWidget(self.chk_global_search)

        btn_do_search = QPushButton("🔍 Cerca")
        btn_do_search.setFixedHeight(34)
        btn_do_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_do_search.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; padding: 0 16px; border-radius: 4px;")
        btn_do_search.clicked.connect(self.search_invoice_items)
        bar_search_items.addWidget(btn_do_search)

        tab_items_layout.addLayout(bar_search_items)

        # Tabella Righe Articoli Fatturati
        self.table_items = QTableWidget()
        self.table_items.setColumnCount(9)
        self.table_items.setHorizontalHeaderLabels([
            "Fornitore", "Data Fattura", "N. Fattura", "Codice Fornitore", 
            "Codice Interno Angeleri", "Descrizione Articolo", "Quantità", "Prezzo Unitario", "Totale Riga"
        ])
        h_it = self.table_items.horizontalHeader()
        h_it.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_it.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_it.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_it.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_it.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        h_it.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        h_it.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        h_it.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        h_it.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self.table_items.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_items.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_items.setSortingEnabled(True)
        self.table_items.cellDoubleClicked.connect(self._on_item_cell_double_clicked)
        self.table_items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_items.customContextMenuRequested.connect(self._show_items_context_menu)
        self.table_items.setToolTip("Fai doppio click su una riga per aprire la relativa fattura completa con PDF/XML.")
        tab_items_layout.addWidget(self.table_items, stretch=1)

        # Barra inferiore azioni articoli fatturati
        items_footer = QHBoxLayout()
        self.lbl_items_count = QLabel("Seleziona un fornitore o digita per cercare tra gli articoli...")
        self.lbl_items_count.setStyleSheet("color: #64748B; font-size: 11px;")
        items_footer.addWidget(self.lbl_items_count, stretch=1)

        self.btn_open_invoice_from_item = QPushButton("📄 Apri Fattura Originale")
        self.btn_open_invoice_from_item.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_invoice_from_item.setStyleSheet("""
            QPushButton {
                background-color: #EA580C;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #C2410C; }
        """)
        self.btn_open_invoice_from_item.clicked.connect(self._open_selected_item_invoice)
        items_footer.addWidget(self.btn_open_invoice_from_item)

        self.btn_link_item = QPushButton("🔗 Collega a Codice Interno")
        self.btn_link_item.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_link_item.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0369A1; }
        """)
        self.btn_link_item.clicked.connect(self._link_selected_invoice_item)
        items_footer.addWidget(self.btn_link_item)

        tab_items_layout.addLayout(items_footer)
        self.supp_tabs.addTab(tab_items_widget, "🔍 Ricerca Articoli in Fattura")

        # ════════════════════════════════════════════════════════
        # TAB 2: ELENCO FATTURE D'ACQUISTO FORNITORE
        # ════════════════════════════════════════════════════════
        self.table_invoices = QTableWidget()
        self.table_invoices.setColumnCount(3)
        self.table_invoices.setHorizontalHeaderLabels(["Numero", "Data", "Importo Lordo"])
        self.table_invoices.horizontalHeader().setStretchLastSection(True)
        self.table_invoices.setToolTip("Fai doppio click su una fattura per aprirne il dettaglio completo con tutti gli articoli e il PDF/XML")
        self.table_invoices.cellDoubleClicked.connect(self._open_invoice_from_table)
        self.supp_tabs.addTab(self.table_invoices, "Fatture di Acquisto")

        # ════════════════════════════════════════════════════════
        # TAB 3: ARTICOLI A CATALOGO FORNITORE (EQUIVALENZE)
        # ════════════════════════════════════════════════════════
        tab_catalog_widget = QWidget()
        tab_catalog_layout = QVBoxLayout(tab_catalog_widget)
        tab_catalog_layout.setContentsMargins(5, 8, 5, 5)
        tab_catalog_layout.setSpacing(6)

        # Tabella Articoli Forniti
        self.table_products = QTableWidget()
        self.table_products.setColumnCount(4)
        self.table_products.setHorizontalHeaderLabels([
            "Codice Fornitore", "Codice Interno Angeleri", "Descrizione Articolo", "Stato Collegamento"
        ])
        h_prod = self.table_products.horizontalHeader()
        h_prod.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_prod.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_prod.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_prod.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_products.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_products.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_products.cellDoubleClicked.connect(self._on_catalog_cell_double_clicked)
        tab_catalog_layout.addWidget(self.table_products, stretch=1)

        # Footer Azioni Catalogo Fornitore
        catalog_footer = QHBoxLayout()
        self.lbl_catalog_count = QLabel("")
        self.lbl_catalog_count.setStyleSheet("color: #64748B; font-size: 11px;")
        catalog_footer.addWidget(self.lbl_catalog_count, stretch=1)

        btn_link_catalog = QPushButton("🔗 Collega / Modifica Codice Interno")
        btn_link_catalog.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link_catalog.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_link_catalog.clicked.connect(self._link_selected_catalog_item)
        catalog_footer.addWidget(btn_link_catalog)

        btn_unlink_catalog = QPushButton("❌ Scollega")
        btn_unlink_catalog.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_unlink_catalog.setStyleSheet("background-color: #F1F5F9; color: #DC2626; border: 1px solid #CBD5E1; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_unlink_catalog.clicked.connect(self._unlink_selected_catalog_item)
        catalog_footer.addWidget(btn_unlink_catalog)

        tab_catalog_layout.addLayout(catalog_footer)
        self.supp_tabs.addTab(tab_catalog_widget, "Articoli a Catalogo Fornitore")

        right_layout.addWidget(self.supp_tabs)
        splitter.addWidget(self.right_panel)

        splitter.setSizes([520, 680])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        layout.addWidget(splitter)

    # ════════════════════════════════════════════════════════
    # CARICAMENTO FORNITORI E DETTAGLIO
    # ════════════════════════════════════════════════════════

    def load_suppliers(self):
        query = self.search_input.text().strip()
        filter_type = self.combo_filter.currentData() or "all"
        data = self.controller.get_suppliers_summary(query, filter_type=filter_type)

        self.table_suppliers.setUpdatesEnabled(False)
        self.table_suppliers.blockSignals(True)
        self.table_suppliers.setSortingEnabled(False)
        self.table_suppliers.clearSelection()
        self.table_suppliers.setRowCount(len(data))

        for i, row in enumerate(data):
            s_id, name, piva, num_fat, tot_spent, last_date, num_art = row
            
            item_name = SortableTableWidgetItem(name or "-")
            item_name.setData(Qt.ItemDataRole.UserRole, s_id)
            item_name.setData(Qt.ItemDataRole.UserRole + 1, name or "")
            self.table_suppliers.setItem(i, 0, item_name)
            
            item_piva = QTableWidgetItem(piva or "-")
            item_piva.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 1, item_piva)

            item_fat = SortableTableWidgetItem(str(num_fat), sort_value=num_fat)
            item_fat.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 2, item_fat)

            item_art = SortableTableWidgetItem(str(num_art), sort_value=num_art)
            item_art.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 3, item_art)

            item_spent = SortableTableWidgetItem(f"€ {tot_spent:,.2f}", sort_value=tot_spent)
            item_spent.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 4, item_spent)
            
            date_str = last_date.strftime("%d/%m/%Y") if last_date else "-"
            item_date = SortableTableWidgetItem(date_str, sort_value=last_date or "")
            item_date.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 5, item_date)

        self.table_suppliers.setSortingEnabled(True)
        if not query and len(data) > 0:
            self.table_suppliers.horizontalHeader().setSortIndicator(4, Qt.SortOrder.DescendingOrder)
        self.table_suppliers.blockSignals(False)
        self.table_suppliers.setUpdatesEnabled(True)

        self.lbl_count.setText(f"Trovati {len(data)} fornitori.")

        if len(data) > 0:
            self.table_suppliers.selectRow(0)
            self.on_supplier_selected()
        else:
            self.clear_detail()

    def clear_detail(self):
        self.current_supplier_id = None
        self.current_supplier_name = ""
        self.lbl_name.setText("-")
        self.lbl_piva.setText("-")
        self.lbl_totals.setText("-")
        self.table_invoices.setRowCount(0)
        self.table_products.setRowCount(0)
        self.table_items.setRowCount(0)
        self.lbl_items_count.setText("Nessun fornitore selezionato.")

    def on_supplier_selected(self):
        row = self.table_suppliers.currentRow()
        supplier_id = None
        supplier_name = ""
        if row >= 0:
            item = self.table_suppliers.item(row, 0)
            if item:
                supplier_id = item.data(Qt.ItemDataRole.UserRole)
                supplier_name = item.data(Qt.ItemDataRole.UserRole + 1) or item.text().strip()

        if not supplier_id:
            selected = self.table_suppliers.selectedItems()
            if selected:
                supplier_id = selected[0].data(Qt.ItemDataRole.UserRole)
                supplier_name = selected[0].data(Qt.ItemDataRole.UserRole + 1) or selected[0].text().strip()

        if not supplier_id:
            return

        self.current_supplier_id = supplier_id
        self.current_supplier_name = supplier_name

        detail = self.controller.get_supplier_detail(supplier_id)
        if not detail:
            return

        supp = detail['supplier']
        invoices = detail['invoices']
        products = detail['products']

        self.lbl_name.setText(supp.name)
        self.lbl_piva.setText(supp.piva or "Non specificata")
        
        tot_spent = sum(inv.total_amount for inv in invoices)
        self.lbl_totals.setText(f"Spesa Totale: € {tot_spent:,.2f}  |  N. Fatture: {len(invoices)}  |  Articoli a Catalogo: {len(products)}")

        # 1. Popola Elenco Fatture
        self.table_invoices.setUpdatesEnabled(False)
        self.table_invoices.blockSignals(True)
        self.table_invoices.setRowCount(len(invoices))
        for i, inv in enumerate(invoices):
            item_num = QTableWidgetItem(inv.number)
            item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
            self.table_invoices.setItem(i, 0, item_num)
            date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
            self.table_invoices.setItem(i, 1, QTableWidgetItem(date_str))
            self.table_invoices.setItem(i, 2, QTableWidgetItem(f"€ {inv.total_amount:,.2f}"))
        self.table_invoices.blockSignals(False)
        self.table_invoices.setUpdatesEnabled(True)

        # 2. Popola Articoli Forniti a Catalogo
        self.table_products.setUpdatesEnabled(False)
        self.table_products.blockSignals(True)
        self.table_products.setRowCount(len(products))
        linked_count = 0
        for i, sp in enumerate(products):
            item_code = QTableWidgetItem(sp.supplier_code)
            item_code.setData(Qt.ItemDataRole.UserRole, sp.id)
            item_code.setData(Qt.ItemDataRole.UserRole + 1, sp.product_id)
            item_code.setData(Qt.ItemDataRole.UserRole + 2, sp.supplier_description)
            self.table_products.setItem(i, 0, item_code)

            master_code = sp.product.code if sp.product else "-"
            self.table_products.setItem(i, 1, QTableWidgetItem(master_code))
            self.table_products.setItem(i, 2, QTableWidgetItem(sp.supplier_description or (sp.product.name if sp.product else "-")))
            
            if sp.product:
                linked_count += 1
                status_item = QTableWidgetItem("🟢 Collegato")
                status_item.setForeground(QBrush(QColor("#15803D")))
            else:
                status_item = QTableWidgetItem("⚪ Da collegare")
                status_item.setForeground(QBrush(QColor("#64748B")))
            self.table_products.setItem(i, 3, status_item)
        self.table_products.blockSignals(False)
        self.table_products.setUpdatesEnabled(True)

        self.lbl_catalog_count.setText(f"{len(products)} articoli registrati ({linked_count} collegati al catalogo Angeleri).")

        # 3. Se la ricerca globale non è attiva, aggiorna la ricerca articoli per questo fornitore
        if not self.chk_global_search.isChecked():
            self.search_invoice_items()

    def _on_global_checkbox_changed(self):
        is_global = self.chk_global_search.isChecked()
        if is_global:
            self.txt_item_search.setPlaceholderText("Ricerca GLOBALE: cerca su TUTTI i fornitori...")
            self.supp_tabs.setTabText(0, "🌐 Ricerca Articoli Globale")
        else:
            self.txt_item_search.setPlaceholderText(f"Cerca articoli nelle fatture di {self.current_supplier_name or 'questo fornitore'}...")
            self.supp_tabs.setTabText(0, "🔍 Ricerca Articoli in Fattura")
        self.search_invoice_items()

    # ════════════════════════════════════════════════════════
    # RICERCA ARTICOLI IN FATTURA (TAB 1)
    # ════════════════════════════════════════════════════════

    def search_invoice_items(self):
        query = self.txt_item_search.text().strip()
        is_global = self.chk_global_search.isChecked()

        if not is_global and not self.current_supplier_id:
            self.table_items.setRowCount(0)
            self.lbl_items_count.setText("Seleziona un fornitore dall'elenco a sinistra.")
            return

        supplier_id = None if is_global else self.current_supplier_id

        items = self.controller.search_supplier_invoice_items(
            query_text=query,
            supplier_id=supplier_id,
            global_search=is_global,
            limit=250
        )

        self.table_items.setUpdatesEnabled(False)
        self.table_items.blockSignals(True)
        self.table_items.setSortingEnabled(False)
        self.table_items.setRowCount(len(items))

        total_net = 0.0
        for i, it in enumerate(items):
            inv = it.invoice
            supp_name = inv.supplier.name if (inv and inv.supplier) else "-"
            
            # 0: Fornitore
            item_supp = SortableTableWidgetItem(supp_name)
            item_supp.setData(Qt.ItemDataRole.UserRole, inv.id if inv else None)
            item_supp.setData(Qt.ItemDataRole.UserRole + 1, inv.supplier_id if inv else None)
            item_supp.setData(Qt.ItemDataRole.UserRole + 2, supp_name)
            self.table_items.setItem(i, 0, item_supp)

            # 1: Data Fattura
            dt = inv.date if inv else None
            dt_str = dt.strftime("%d/%m/%Y") if dt else "-"
            self.table_items.setItem(i, 1, SortableTableWidgetItem(dt_str, sort_value=dt or ""))

            # 2: N. Fattura
            inv_num = inv.number if inv else "-"
            item_inv_num = SortableTableWidgetItem(inv_num)
            item_inv_num.setData(Qt.ItemDataRole.UserRole, inv.id if inv else None)
            self.table_items.setItem(i, 2, item_inv_num)

            # 3: Codice Fornitore (Raw Code in fattura)
            raw_code = it.code or it.customer_code or "-"
            item_raw = SortableTableWidgetItem(raw_code)
            item_raw.setData(Qt.ItemDataRole.UserRole, raw_code)
            self.table_items.setItem(i, 3, item_raw)

            # 4: Codice Interno Angeleri
            master_code = it.product.code if it.product else "-"
            item_master = SortableTableWidgetItem(master_code)
            item_master.setData(Qt.ItemDataRole.UserRole, it.product_id)
            if it.product:
                item_master.setForeground(QBrush(QColor("#0284C7")))
                item_master.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            else:
                item_master.setForeground(QBrush(QColor("#94A3B8")))
            self.table_items.setItem(i, 4, item_master)

            # 5: Descrizione Articolo
            self.table_items.setItem(i, 5, QTableWidgetItem(it.description or "-"))

            # 6: Quantità
            qty = it.quantity or 0.0
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:,.2f}".rstrip('0').rstrip('.')
            item_qty = SortableTableWidgetItem(qty_str, sort_value=qty)
            item_qty.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_items.setItem(i, 6, item_qty)

            # 7: Prezzo Unitario
            pr = it.unit_price or 0.0
            item_pr = SortableTableWidgetItem(f"€ {pr:,.2f}", sort_value=pr)
            item_pr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_items.setItem(i, 7, item_pr)

            # 8: Totale Riga
            tot = it.total_price or 0.0
            total_net += tot
            item_tot = SortableTableWidgetItem(f"€ {tot:,.2f}", sort_value=tot)
            item_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_items.setItem(i, 8, item_tot)

        self.table_items.setSortingEnabled(True)
        self.table_items.blockSignals(False)
        self.table_items.setUpdatesEnabled(True)

        mode_str = "Globale (tutti i fornitori)" if is_global else f"Fornitore '{self.current_supplier_name}'"
        query_str = f" per '{query}'" if query else ""
        self.lbl_items_count.setText(
            f"<b>{len(items)} articoli trovati</b>{query_str} [{mode_str}]  •  Totale spesa righe: <b>€ {total_net:,.2f}</b>"
        )

    def _on_item_cell_double_clicked(self, row, col):
        """Doppio click su una riga articolo: apre direttamente la relativa fattura."""
        item = self.table_items.item(row, 0)
        if not item:
            return
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id:
            self._open_invoice_by_id(inv_id)

    def _open_selected_item_invoice(self):
        """Pulsante: apre la fattura della riga attualmente selezionata."""
        row = self.table_items.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selezione Richiesta", "Seleziona prima una riga articolo per aprirne la fattura.")
            return
        item = self.table_items.item(row, 0)
        if item:
            inv_id = item.data(Qt.ItemDataRole.UserRole)
            if inv_id:
                self._open_invoice_by_id(inv_id)

    def _open_invoice_by_id(self, inv_id: int):
        if inv_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=inv_id, invoice_type="purchase")
        elif inv_id:
            from app.ui.invoice_detail import InvoiceDetailDialog
            self._invoice_dlg = InvoiceDetailDialog(invoice_id=inv_id, invoice_type="purchase", parent=None)
            self._invoice_dlg.show()

    def _link_selected_invoice_item(self):
        """Apre il dialog per collegare l'articolo fornitore selezionato al catalogo master Angeleri."""
        row = self.table_items.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selezione Richiesta", "Seleziona una riga articolo dalla tabella per collegarla.")
            return

        item_supp = self.table_items.item(row, 0)
        item_raw = self.table_items.item(row, 3)
        item_master = self.table_items.item(row, 4)
        item_desc = self.table_items.item(row, 5)

        supp_id = item_supp.data(Qt.ItemDataRole.UserRole + 1) or self.current_supplier_id
        supp_name = item_supp.data(Qt.ItemDataRole.UserRole + 2) or self.current_supplier_name
        raw_code = item_raw.text().strip() if item_raw else ""
        desc = item_desc.text().strip() if item_desc else ""
        curr_prod_id = item_master.data(Qt.ItemDataRole.UserRole) if item_master else None

        if not supp_id or not raw_code or raw_code == "-":
            QMessageBox.warning(self, "Articolo Non Valido", "La riga selezionata non contiene un codice articolo valido da associare.")
            return

        dlg = ProductLinkDialog(
            controller=self.controller,
            supplier_id=supp_id,
            supplier_name=supp_name,
            supplier_code=raw_code,
            supplier_desc=desc,
            current_product_id=curr_prod_id,
            parent=self
        )
        if dlg.exec():
            # Ricarica sia la ricerca articoli sia il dettaglio fornitore
            self.search_invoice_items()
            if self.current_supplier_id:
                self.on_supplier_selected()

    def _show_items_context_menu(self, pos):
        row = self.table_items.currentRow()
        if row < 0:
            return

        menu = QMenu(self)
        act_open = QAction("📄 Apri Fattura Originale (PDF / XML)", self)
        act_open.triggered.connect(self._open_selected_item_invoice)
        menu.addAction(act_open)

        act_link = QAction("🔗 Collega / Assegna Codice Interno Angeleri", self)
        act_link.triggered.connect(self._link_selected_invoice_item)
        menu.addAction(act_link)

        menu.addSeparator()
        act_copy = QAction("📋 Copia Dati Riga", self)
        act_copy.triggered.connect(self._copy_selected_item_text)
        menu.addAction(act_copy)

        menu.exec(self.table_items.viewport().mapToGlobal(pos))

    def _copy_selected_item_text(self):
        row = self.table_items.currentRow()
        if row < 0:
            return
        vals = [self.table_items.item(row, col).text() for col in range(self.table_items.columnCount()) if self.table_items.item(row, col)]
        line = " | ".join(vals)
        QApplication.clipboard().setText(line)

    # ════════════════════════════════════════════════════════
    # TAB 2 & 3: FATTURE E CATALOGO FORNITORE
    # ════════════════════════════════════════════════════════

    def _open_invoice_from_table(self, row, col):
        item = self.table_invoices.item(row, 0)
        if not item:
            return
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id:
            self._open_invoice_by_id(inv_id)

    def _on_catalog_cell_double_clicked(self, row, col):
        self._link_selected_catalog_item()

    def _link_selected_catalog_item(self):
        row = self.table_products.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selezione Richiesta", "Seleziona un articolo fornitore dal catalogo.")
            return

        item_code = self.table_products.item(row, 0)
        item_master = self.table_products.item(row, 1)
        item_desc = self.table_products.item(row, 2)

        supplier_code = item_code.text().strip() if item_code else ""
        supplier_desc = item_desc.text().strip() if item_desc else ""
        curr_prod_id = item_code.data(Qt.ItemDataRole.UserRole + 1) if item_code else None

        if not self.current_supplier_id or not supplier_code:
            return

        dlg = ProductLinkDialog(
            controller=self.controller,
            supplier_id=self.current_supplier_id,
            supplier_name=self.current_supplier_name,
            supplier_code=supplier_code,
            supplier_desc=supplier_desc,
            current_product_id=curr_prod_id,
            parent=self
        )
        if dlg.exec():
            self.on_supplier_selected()
            self.search_invoice_items()

    def _unlink_selected_catalog_item(self):
        row = self.table_products.currentRow()
        if row < 0:
            return

        item_code = self.table_products.item(row, 0)
        sp_id = item_code.data(Qt.ItemDataRole.UserRole) if item_code else None
        if not sp_id:
            return

        reply = QMessageBox.question(
            self,
            "Conferma Scollegamento",
            "Vuoi rimuovere il collegamento tra questo articolo fornitore e l'articolo master?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.unlink_supplier_product(sp_id)
            self.on_supplier_selected()
            self.search_invoice_items()

    def refresh_data(self):
        self.load_suppliers()
