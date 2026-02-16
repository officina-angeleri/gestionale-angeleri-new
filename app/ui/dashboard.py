from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from app.utils.ui_utils import SortableTableWidgetItem

class StatCard(QFrame):
    def __init__(self, title, value, color="#FFFFFF"):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"background-color: {color}; border-radius: 10px; padding: 10px;")
        
        layout = QVBoxLayout()
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #666; font-size: 14px;")
        
        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet("color: #333; font-size: 24px; font-weight: bold;")
        
        layout.addWidget(lbl_title)
        layout.addWidget(self.value_label)
        self.setLayout(layout)

    def set_value(self, value):
        self.value_label.setText(str(value))

class DashboardWidget(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Dashboard Analisi Fatture")
        title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        main_layout.addWidget(title)
        
        # Stats Row
        stats_layout = QHBoxLayout()
        self.card_total_gross = StatCard("Totale Lordo (IVA)", "€ 0.00", "#E3F2FD")
        self.card_total_net = StatCard("Totale Netto (Imp.)", "€ 0.00", "#E8F5E9")
        self.card_invoice_count = StatCard("Fatture Analizzate", "0", "#F3E5F5")
        self.card_top_supplier = StatCard("Top Fornitore", "-", "#FFF3E0")
        
        stats_layout.addWidget(self.card_total_gross)
        stats_layout.addWidget(self.card_total_net)
        stats_layout.addWidget(self.card_invoice_count)
        stats_layout.addWidget(self.card_top_supplier)
        
        main_layout.addLayout(stats_layout)
        
        # Supplier Table
        lbl_list = QLabel("Elenco Fornitori per Spesa (Lorda)")
        lbl_list.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        lbl_list.setContentsMargins(0, 10, 0, 5)
        main_layout.addWidget(lbl_list)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Fornitore", "Spesa Lorda Totale"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 200)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        
        main_layout.addWidget(self.table)
        
        self.setLayout(main_layout)
        self.refresh_data()
        
    def refresh_data(self):
        stats = self.controller.get_dashboard_stats()
        
        # Update cards
        self.card_total_gross.set_value(f"€ {stats['total_gross']:,.2f}")
        self.card_total_net.set_value(f"€ {stats['total_net']:,.2f}")
        self.card_invoice_count.set_value(str(stats['total_count']))
        
        if stats['top_suppliers']:
            top = stats['top_suppliers'][0]
            self.card_top_supplier.set_value(f"{top[0]} (€ {top[1]:.0f})")
        else:
            self.card_top_supplier.set_value("-")
        
        # Update Table
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for name, value in stats['top_suppliers']:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            name_item = QTableWidgetItem(name)
            val_item = SortableTableWidgetItem(f"€ {value:,.2f}", sort_value=value)
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_item.setForeground(QColor("#1565C0"))
            
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, val_item)
            
        self.table.setSortingEnabled(True)
        # Default sort by spend (column 1) descending
        self.table.sortItems(1, Qt.SortOrder.DescendingOrder)
