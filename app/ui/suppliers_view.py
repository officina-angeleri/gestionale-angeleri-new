from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QSplitter, QTabWidget, QGroupBox, QFormLayout, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from app.utils.ui_utils import SortableTableWidgetItem

class SuppliersWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.setup_ui()
        self.load_suppliers()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Top Bar
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
        self.search_input.textChanged.connect(self.load_suppliers)
        top_layout.addWidget(self.search_input)

        btn_refresh = QPushButton("Aggiorna")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self.load_suppliers)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # PANNELLO SINISTRO: Tabella Fornitori
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
        self.lbl_count.setStyleSheet("color: #666; font-size: 12px;")
        left_layout.addWidget(self.lbl_count)
        splitter.addWidget(left_panel)

        # PANNELLO DESTRO: Scheda Fornitore
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

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

        # Tabs: Fatture vs Articoli a catalogo
        self.supp_tabs = QTabWidget()

        # Tab Fatture
        self.table_invoices = QTableWidget()
        self.table_invoices.setColumnCount(3)
        self.table_invoices.setHorizontalHeaderLabels(["Numero", "Data", "Importo Lordo"])
        self.table_invoices.horizontalHeader().setStretchLastSection(True)
        self.table_invoices.setToolTip("Fai doppio click su una fattura per aprirne il dettaglio completo con tutti gli articoli e il PDF/XML")
        self.table_invoices.cellDoubleClicked.connect(self._open_invoice_from_table)
        self.supp_tabs.addTab(self.table_invoices, "Fatture di Acquisto")

        # Tab Articoli Forniti
        self.table_products = QTableWidget()
        self.table_products.setColumnCount(3)
        self.table_products.setHorizontalHeaderLabels(["Codice Fornitore", "Codice Interno Angeleri", "Descrizione Articolo"])
        self.table_products.horizontalHeader().setStretchLastSection(True)
        self.supp_tabs.addTab(self.table_products, "Articoli a Catalogo Fornitore")

        right_layout.addWidget(self.supp_tabs)
        splitter.addWidget(self.right_panel)

        splitter.setSizes([650, 480])
        layout.addWidget(splitter)

    def load_suppliers(self):
        query = self.search_input.text().strip()
        filter_type = self.combo_filter.currentData() or "all"
        data = self.controller.get_suppliers_summary(query, filter_type=filter_type)

        self.table_suppliers.setSortingEnabled(False)
        self.table_suppliers.setRowCount(len(data))

        for i, row in enumerate(data):
            s_id, name, piva, num_fat, tot_spent, last_date, num_art = row
            
            item_name = SortableTableWidgetItem(name or "-")
            item_name.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table_suppliers.setItem(i, 0, item_name)
            
            self.table_suppliers.setItem(i, 1, QTableWidgetItem(piva or "-"))
            self.table_suppliers.setItem(i, 2, SortableTableWidgetItem(str(num_fat), sort_value=num_fat))
            self.table_suppliers.setItem(i, 3, SortableTableWidgetItem(str(num_art), sort_value=num_art))
            self.table_suppliers.setItem(i, 4, SortableTableWidgetItem(f"€ {tot_spent:,.2f}", sort_value=tot_spent))
            
            date_str = last_date.strftime("%d/%m/%Y") if last_date else "-"
            self.table_suppliers.setItem(i, 5, SortableTableWidgetItem(date_str, sort_value=last_date or ""))

        self.table_suppliers.setSortingEnabled(True)
        # Se non c'è una ricerca attiva, mantieni ordinamento per spesa totale decrescente
        if not query and len(data) > 0:
            self.table_suppliers.sortByColumn(4, Qt.SortOrder.DescendingOrder)

        self.lbl_count.setText(f"Trovati {len(data)} fornitori.")

        if len(data) > 0 and not self.table_suppliers.selectedItems():
            self.table_suppliers.selectRow(0)

    def on_supplier_selected(self):
        selected = self.table_suppliers.selectedItems()
        if not selected:
            return
        supplier_id = selected[0].data(Qt.ItemDataRole.UserRole)
        if not supplier_id:
            return

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

        # Popola Fatture
        self.table_invoices.setRowCount(len(invoices))
        for i, inv in enumerate(invoices):
            item_num = QTableWidgetItem(inv.number)
            item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
            self.table_invoices.setItem(i, 0, item_num)
            date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
            self.table_invoices.setItem(i, 1, QTableWidgetItem(date_str))
            self.table_invoices.setItem(i, 2, QTableWidgetItem(f"€ {inv.total_amount:,.2f}"))

        # Popola Articoli Forniti
        self.table_products.setRowCount(len(products))
        for i, sp in enumerate(products):
            self.table_products.setItem(i, 0, QTableWidgetItem(sp.supplier_code))
            master_code = sp.product.code if sp.product else "-"
            self.table_products.setItem(i, 1, QTableWidgetItem(master_code))
            self.table_products.setItem(i, 2, QTableWidgetItem(sp.supplier_description or (sp.product.name if sp.product else "-")))

    def _open_invoice_from_table(self, row, col):
        item = self.table_invoices.item(row, 0)
        if not item:
            return
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=inv_id, invoice_type="purchase")
        elif inv_id:
            from app.ui.invoice_detail import InvoiceDetailDialog
            self._invoice_dlg = InvoiceDetailDialog(invoice_id=inv_id, invoice_type="purchase", parent=None)
            self._invoice_dlg.show()

    def refresh_data(self):
        self.load_suppliers()
