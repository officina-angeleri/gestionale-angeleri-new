from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
import re
from app.utils.ui_utils import SortableTableWidgetItem

class ArticleSearchWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.active_search_steps = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Titolo
        title = QLabel("Ricerca Articoli nelle Fatture")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca articoli (es: vite inox %M6)...")
        self.search_input.setFixedHeight(40)
        self.search_input.setStyleSheet("font-size: 14px; padding-left: 10px;")
        self.search_input.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        
        btn_search = QPushButton("CERCA")
        btn_search.setFixedHeight(40)
        btn_search.setFixedWidth(100)
        btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_search.clicked.connect(self.perform_search)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)
        
        # Opzioni di ricerca
        options_layout = QHBoxLayout()
        self.cb_code = QCheckBox("Codice articolo")
        self.cb_desc = QCheckBox("Descrizione articolo")
        self.cb_code.setChecked(True)
        self.cb_desc.setChecked(True)
        options_layout.addWidget(self.cb_code)
        options_layout.addWidget(self.cb_desc)
        
        options_layout.addSpacing(20)
        
        # Ricerca incrementale
        self.cb_incremental = QCheckBox("Ricerca incrementale")
        self.cb_incremental.setToolTip("Filtra i risultati correnti aggiungendo nuove parole chiave")
        self.cb_incremental.stateChanged.connect(self.update_mode_label)
        options_layout.addWidget(self.cb_incremental)
        
        self.lbl_mode = QLabel("Modalità: Nuova ricerca")
        self.lbl_mode.setStyleSheet("color: #666; font-style: italic;")
        options_layout.addWidget(self.lbl_mode)
        
        options_layout.addStretch()
        layout.addLayout(options_layout)
        
        # Tabella Risultati
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Fattura", "Data", "Fornitore", "Cod. Art.", 
            "Descrizione", "Q.tà", "Prezzo", "Totale"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self.handle_double_click)
        layout.addWidget(self.table)
        
        # Status Bar interna
        self.status_label = QLabel("Pronto per la ricerca.")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

    def update_mode_label(self):
        if self.cb_incremental.isChecked():
            self.lbl_mode.setText("Modalità: Ricerca incrementale")
            self.lbl_mode.setStyleSheet("color: #1565C0; font-weight: bold;")
        else:
            self.lbl_mode.setText("Modalità: Nuova ricerca")
            self.lbl_mode.setStyleSheet("color: #666; font-style: italic;")
            self.active_search_steps = []

    def perform_search(self):
        text = self.search_input.text().strip()
        if not text:
            # Se vuoto e non siamo in incrementale, pulisci
            if not self.cb_incremental.isChecked():
                self.table.setRowCount(0)
                self.active_search_steps = []
            return
            
        # Split by both space AND % to treat them as AND filters in any order
        words = [w for w in re.split(r'[\s%]+', text) if w]
        
        search_code = self.cb_code.isChecked()
        search_desc = self.cb_desc.isChecked()
        
        if not search_code and not search_desc:
            search_code = search_desc = True # Fallback
            
        current_step = {
            'words': words,
            'search_code': search_code,
            'search_desc': search_desc
        }
        
        if not self.cb_incremental.isChecked():
            self.active_search_steps = [current_step]
        else:
            self.active_search_steps.append(current_step)
            
        try:
            results = self.controller.search_items(self.active_search_steps)
            self.display_results(results)
            self.status_label.setText(f"Trovate {len(results)} righe.")
        except Exception as e:
            self.status_label.setText(f"Errore: {e}")
            if self.cb_incremental.isChecked():
                self.active_search_steps.pop()

    def display_results(self, results):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        
        for i, riga in enumerate(results):
            # Invoice Info
            # Store invoice ID in UserRole for retrieval
            item_num = SortableTableWidgetItem(str(riga.invoice.number), sort_value=riga.invoice.number)
            item_num.setData(Qt.ItemDataRole.UserRole, riga.invoice.id)
            
            self.table.setItem(i, 0, item_num)
            
            # DATE SORTING: use native date object
            date_str = riga.invoice.date.strftime("%d/%m/%Y") if riga.invoice.date else "-"
            self.table.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=riga.invoice.date))
            
            self.table.setItem(i, 2, QTableWidgetItem(riga.invoice.supplier.name))
            
            # Item Info
            self.table.setItem(i, 3, QTableWidgetItem(riga.code or "-"))
            self.table.setItem(i, 4, QTableWidgetItem(riga.description))
            
            # Numeric Items for sorting
            self.table.setItem(i, 5, SortableTableWidgetItem(f"{riga.quantity:.2f}", sort_value=riga.quantity))
            self.table.setItem(i, 6, SortableTableWidgetItem(f"€ {riga.unit_price:.2f}", sort_value=riga.unit_price))
            self.table.setItem(i, 7, SortableTableWidgetItem(f"€ {riga.total_price:.2f}", sort_value=riga.total_price))
            
        self.table.setSortingEnabled(True)

    def handle_double_click(self, row, col):
        invoice_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if invoice_id and hasattr(self.main_window, 'show_invoice_detail_by_id'):
            self.main_window.show_invoice_detail_by_id(invoice_id)

    def refresh_data(self):
        """Called when manually refreshing via toolbar button"""
        if self.active_search_steps:
            self.perform_search()
