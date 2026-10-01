from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QSplitter, QTabWidget, QGroupBox, QFormLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from app.utils.ui_utils import SortableTableWidgetItem

class CustomersWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.setup_ui()
        self.load_customers()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Barra superiore: Titolo e Ricerca
        top_layout = QHBoxLayout()
        title = QLabel("👥 Anagrafica Clienti")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca cliente per nome o P.IVA...")
        self.search_input.setFixedWidth(300)
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self.load_customers)
        top_layout.addWidget(self.search_input)

        btn_refresh = QPushButton("Aggiorna")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self.load_customers)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        # Splitter Orizzontale: Sinistra (Elenco Clienti) | Destra (Scheda 360° Cliente)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # PANNELLO SINISTRO: Tabella Clienti
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table_customers = QTableWidget()
        self.table_customers.setColumnCount(6)
        self.table_customers.setHorizontalHeaderLabels([
            "Cliente / Ragione Sociale", "P.IVA / C.F.", "Nazione", "Fatture", "Fatturato Totale", "Ultima Fattura"
        ])
        h_cust = self.table_customers.horizontalHeader()
        h_cust.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_cust.setStretchLastSection(True)
        self.table_customers.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_customers.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_customers.setSortingEnabled(True)
        self.table_customers.itemSelectionChanged.connect(self.on_customer_selected)
        self.table_customers.cellClicked.connect(lambda r, c: self.on_customer_selected())
        left_layout.addWidget(self.table_customers)

        self.lbl_count = QLabel("Caricamento clienti...")
        self.lbl_count.setStyleSheet("color: #666; font-size: 12px;")
        left_layout.addWidget(self.lbl_count)
        splitter.addWidget(left_panel)

        # PANNELLO DESTRO: Scheda Dettaglio Cliente
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Intestazione Scheda
        self.box_info = QGroupBox("Scheda Dettaglio Cliente")
        self.box_info.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        info_layout = QFormLayout(self.box_info)

        self.lbl_name = QLabel("-")
        self.lbl_name.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_piva = QLabel("-")
        self.lbl_address = QLabel("-")
        self.lbl_totals = QLabel("-")
        self.lbl_totals.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 13px;")

        info_layout.addRow("Ragione Sociale:", self.lbl_name)
        info_layout.addRow("P.IVA / Cod. Fiscale:", self.lbl_piva)
        info_layout.addRow("Sede:", self.lbl_address)
        info_layout.addRow("Riepilogo Vendite:", self.lbl_totals)

        right_layout.addWidget(self.box_info)

        # Tabs: Fatture emesse vs Ricambi acquistati
        self.client_tabs = QTabWidget()

        # Tab Fatture
        self.table_invoices = QTableWidget()
        self.table_invoices.setColumnCount(4)
        self.table_invoices.setHorizontalHeaderLabels(["Numero", "Data", "Tipo Documento", "Totale Fattura"])
        self.table_invoices.horizontalHeader().setStretchLastSection(True)
        self.table_invoices.setToolTip("Fai doppio click su una fattura per aprirne il dettaglio completo con tutti gli articoli e il PDF")
        self.table_invoices.cellDoubleClicked.connect(self._open_invoice_from_table)
        self.client_tabs.addTab(self.table_invoices, "Fatture Emesse")

        # Tab Ricambi & Macchine
        self.table_items = QTableWidget()
        self.table_items.setColumnCount(7)
        self.table_items.setHorizontalHeaderLabels([
            "Data", "Fattura", "Codice", "Descrizione", "Q.tà", "Prezzo Vendita", "Sconto %"
        ])
        self.table_items.horizontalHeader().setStretchLastSection(True)
        self.table_items.setToolTip("Fai doppio click per aprire la fattura originale in cui è contenuto l'articolo")
        self.table_items.cellDoubleClicked.connect(self._open_invoice_from_items)
        self.client_tabs.addTab(self.table_items, "Ricambi & Macchinari Acquistati")

        right_layout.addWidget(self.client_tabs)
        splitter.addWidget(self.right_panel)

        splitter.setSizes([600, 500])
        layout.addWidget(splitter)

    def load_customers(self):
        query = self.search_input.text().strip()
        data = self.controller.get_customers_summary(query)

        self.table_customers.blockSignals(True)
        self.table_customers.setSortingEnabled(False)
        self.table_customers.clearSelection()
        self.table_customers.setRowCount(len(data))

        for i, row in enumerate(data):
            c_id, name, piva, country, num_fat, tot_rev, last_date = row
            
            item_name = SortableTableWidgetItem(name or "-")
            item_name.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 0, item_name)
            
            item_piva = QTableWidgetItem(piva or "-")
            item_piva.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 1, item_piva)

            item_country = QTableWidgetItem(country or "IT")
            item_country.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 2, item_country)

            item_num = SortableTableWidgetItem(str(num_fat), sort_value=num_fat)
            item_num.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 3, item_num)

            item_rev = SortableTableWidgetItem(f"€ {tot_rev:,.2f}", sort_value=tot_rev)
            item_rev.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 4, item_rev)
            
            date_str = last_date.strftime("%d/%m/%Y") if last_date else "-"
            item_date = SortableTableWidgetItem(date_str, sort_value=last_date or "")
            item_date.setData(Qt.ItemDataRole.UserRole, c_id)
            self.table_customers.setItem(i, 5, item_date)

        self.table_customers.setSortingEnabled(True)
        self.table_customers.blockSignals(False)
        self.lbl_count.setText(f"Trovati {len(data)} clienti.")

        if len(data) > 0:
            self.table_customers.selectRow(0)
            self.on_customer_selected()
        else:
            self.clear_detail()

    def clear_detail(self):
        self.lbl_name.setText("-")
        self.lbl_piva.setText("-")
        self.lbl_address.setText("-")
        self.lbl_totals.setText("-")
        self.table_invoices.setRowCount(0)
        self.table_items.setRowCount(0)

    def on_customer_selected(self):
        row = self.table_customers.currentRow()
        customer_id = None
        if row >= 0:
            item = self.table_customers.item(row, 0)
            if item:
                customer_id = item.data(Qt.ItemDataRole.UserRole)

        if not customer_id:
            selected = self.table_customers.selectedItems()
            if selected:
                customer_id = selected[0].data(Qt.ItemDataRole.UserRole)
                if not customer_id and selected[0].row() >= 0:
                    it0 = self.table_customers.item(selected[0].row(), 0)
                    if it0:
                        customer_id = it0.data(Qt.ItemDataRole.UserRole)

        if not customer_id:
            return

        detail = self.controller.get_customer_detail(customer_id)
        if not detail:
            return

        cust = detail['customer']
        invoices = detail['invoices']
        items = detail['items']

        self.lbl_name.setText(cust.name)
        self.lbl_piva.setText(cust.piva_cf or "Non specificata")
        self.lbl_address.setText(f"{cust.address or ''} ({cust.country or 'IT'})")
        
        tot_rev = sum(inv.total_amount for inv in invoices)
        self.lbl_totals.setText(f"Totale Fatturato: € {tot_rev:,.2f}  |  N. Fatture: {len(invoices)}")

        # Popola Fatture
        self.table_invoices.setRowCount(len(invoices))
        for i, inv in enumerate(invoices):
            item_num = QTableWidgetItem(f"{inv.number}/{inv.year}")
            item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
            self.table_invoices.setItem(i, 0, item_num)
            date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
            self.table_invoices.setItem(i, 1, QTableWidgetItem(date_str))
            self.table_invoices.setItem(i, 2, QTableWidgetItem(inv.doc_type or "TD24"))
            self.table_invoices.setItem(i, 3, QTableWidgetItem(f"€ {inv.total_amount:,.2f}"))

        # Popola Articoli
        self.table_items.setRowCount(len(items))
        for i, it in enumerate(items):
            date_str = it.invoice.date.strftime("%d/%m/%Y") if it.invoice and it.invoice.date else "-"
            inv_ref = f"{it.invoice.number}/{it.invoice.year}" if it.invoice else "-"
            
            self.table_items.setItem(i, 0, QTableWidgetItem(date_str))
            item_ref = QTableWidgetItem(inv_ref)
            if it.invoice:
                item_ref.setData(Qt.ItemDataRole.UserRole, it.invoice.id)
            self.table_items.setItem(i, 1, item_ref)
            self.table_items.setItem(i, 2, QTableWidgetItem(it.raw_code or "-"))
            self.table_items.setItem(i, 3, QTableWidgetItem(it.description))
            self.table_items.setItem(i, 4, QTableWidgetItem(f"{it.quantity:.2f}"))
            self.table_items.setItem(i, 5, QTableWidgetItem(f"€ {it.unit_price:.2f}"))
            self.table_items.setItem(i, 6, QTableWidgetItem(f"{it.discount:.1f}%" if it.discount else "-"))

    def _open_invoice_from_table(self, row, col):
        item = self.table_invoices.item(row, 0)
        if not item:
            return
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=inv_id, invoice_type="sale")
        elif inv_id:
            from app.ui.invoice_detail import InvoiceDetailDialog
            self._invoice_dlg = InvoiceDetailDialog(invoice_id=inv_id, invoice_type="sale", parent=None)
            self._invoice_dlg.show()

    def _open_invoice_from_items(self, row, col):
        item = self.table_items.item(row, 1)
        if not item:
            return
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=inv_id, invoice_type="sale")
        elif inv_id:
            from app.ui.invoice_detail import InvoiceDetailDialog
            self._invoice_dlg = InvoiceDetailDialog(invoice_id=inv_id, invoice_type="sale", parent=None)
            self._invoice_dlg.show()

    def refresh_data(self):
        self.load_customers()
