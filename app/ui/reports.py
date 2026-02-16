from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHBoxLayout, QLabel, QHeaderView, QPushButton, QComboBox)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from app.utils.ui_utils import SortableTableWidgetItem
from app.controllers.analysis_engine import AnalysisEngine

class ReportWidget(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.engine = AnalysisEngine()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Report Acquisti per Fornitore e Anno")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header_layout.addWidget(title)
        
        btn_refresh = QPushButton("Aggiorna Report")
        btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(btn_refresh)
        
        layout.addLayout(header_layout)
        
        # Filtri
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Filtra Fornitore:"))
        self.combo_supplier = QComboBox()
        self.combo_supplier.addItem("Tutti")
        self.combo_supplier.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.combo_supplier)
        
        filter_layout.addWidget(QLabel("Filtra Anno:"))
        self.combo_year = QComboBox()
        self.combo_year.addItem("Tutti")
        self.combo_year.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.combo_year)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Fornitore", "Anno", "Num. Fatture", "Costo Netto (Imp.)", "Totale Lordo (IVA)"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Summary Row
        summary_layout = QHBoxLayout()
        summary_layout.addStretch()
        
        self.lbl_total_invoices = QLabel("Fatture Totali: 0")
        self.lbl_total_invoices.setStyleSheet("font-size: 14px; color: #555;")
        summary_layout.addWidget(self.lbl_total_invoices)
        
        summary_layout.addSpacing(30)
        
        self.lbl_grand_net = QLabel("Totale Netto: € 0.00")
        self.lbl_grand_net.setStyleSheet("font-size: 15px; font-weight: bold; color: #2E7D32; background-color: #E8F5E9; padding: 5px 15px; border-radius: 5px;")
        summary_layout.addWidget(self.lbl_grand_net)

        summary_layout.addSpacing(15)
        
        self.lbl_grand_gross = QLabel("Totale Lordo: € 0.00")
        self.lbl_grand_gross.setStyleSheet("font-size: 15px; font-weight: bold; color: #1565C0; background-color: #E3F2FD; padding: 5px 15px; border-radius: 5px;")
        summary_layout.addWidget(self.lbl_grand_gross)
        
        layout.addLayout(summary_layout)
        
        self.setLayout(layout)
        self.refresh_data()
        
    def refresh_data(self):
        self.table.setSortingEnabled(False)
        self.data = self.engine.get_supplier_reports()
        
        # Update Combos
        current_supp = self.combo_supplier.currentText()
        current_year = self.combo_year.currentText()
        
        suppliers = sorted(list(set(d['Fornitore'] for d in self.data)))
        years = sorted(list(set(d['Anno'] for d in self.data)), reverse=True)
        
        self.combo_supplier.blockSignals(True)
        self.combo_supplier.clear()
        self.combo_supplier.addItem("Tutti")
        self.combo_supplier.addItems(suppliers)
        index = self.combo_supplier.findText(current_supp)
        if index >= 0: self.combo_supplier.setCurrentIndex(index)
        self.combo_supplier.blockSignals(False)
        
        self.combo_year.blockSignals(True)
        self.combo_year.clear()
        self.combo_year.addItem("Tutti")
        self.combo_year.addItems(years)
        index = self.combo_year.findText(current_year)
        if index >= 0: self.combo_year.setCurrentIndex(index)
        self.combo_year.blockSignals(False)
        
        self.apply_filters()
        self.table.setSortingEnabled(True)
        
    def apply_filters(self):
        supp_filter = self.combo_supplier.currentText()
        year_filter = self.combo_year.currentText()
        
        filtered_data = [
            d for d in self.data 
            if (supp_filter == "Tutti" or d['Fornitore'] == supp_filter) and
               (year_filter == "Tutti" or d['Anno'] == year_filter)
        ]
        
        self.table.setRowCount(len(filtered_data))
        grand_total_net = 0.0
        grand_total_gross = 0.0
        total_invoices = 0
        
        for i, row in enumerate(filtered_data):
            self.table.setItem(i, 0, QTableWidgetItem(row['Fornitore']))
            self.table.setItem(i, 1, SortableTableWidgetItem(str(row['Anno']), sort_value=row['Anno']))
            
            num_item = SortableTableWidgetItem(str(row['NumFatture']), sort_value=row['NumFatture'])
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, num_item)
            
            # Colonna Netto
            net_val = row['TotaleNetto'] or 0.0
            net_item = SortableTableWidgetItem(f"€ {net_val:,.2f}", sort_value=net_val)
            net_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            net_item.setForeground(QColor("#2E7D32")) # Green
            self.table.setItem(i, 3, net_item)

            # Colonna Lordo
            gross_val = row['TotaleLordo'] or 0.0
            gross_item = SortableTableWidgetItem(f"€ {gross_val:,.2f}", sort_value=gross_val)
            gross_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            gross_item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
            gross_item.setForeground(QColor("#1565C0")) # Blue
            self.table.setItem(i, 4, gross_item)
            
            grand_total_net += net_val
            grand_total_gross += gross_val
            total_invoices += row['NumFatture']
            
        # Aggiorna Etichette Riassuntive
        self.lbl_grand_net.setText(f"Imp. Netto: € {grand_total_net:,.2f}")
        self.lbl_grand_gross.setText(f"Tot. Lordo: € {grand_total_gross:,.2f}")
        self.lbl_total_invoices.setText(f"Fatture Totali: {total_invoices}")
