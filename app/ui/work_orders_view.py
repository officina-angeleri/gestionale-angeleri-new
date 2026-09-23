from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QComboBox, QDialog, QFormLayout, QTextEdit, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from app.utils.ui_utils import SortableTableWidgetItem

class NewWorkOrderDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Nuova Scheda Lavoro / Commessa")
        self.setFixedSize(500, 360)
        
        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.combo_customer = QComboBox()
        self.combo_customer.setFixedHeight(34)
        customers = self.controller.get_customers_summary()
        for row in customers:
            c_id, name, piva, country, _, _, _ = row
            self.combo_customer.addItem(f"{name} ({country or 'IT'})", userData=c_id)
        layout.addRow("Cliente:", self.combo_customer)

        self.edit_machine = QLineEdit()
        self.edit_machine.setPlaceholderText("es. MAV 3150, ICT 60, ECOL 4150...")
        self.edit_machine.setFixedHeight(34)
        layout.addRow("Modello Macchina:", self.edit_machine)

        self.edit_serial = QLineEdit()
        self.edit_serial.setPlaceholderText("Matricola macchinario (opzionale)")
        self.edit_serial.setFixedHeight(34)
        layout.addRow("Matricola:", self.edit_serial)

        self.edit_notes = QTextEdit()
        self.edit_notes.setPlaceholderText("Descrizione del guasto, lavorazione richiesta o pezzi da sostituire...")
        self.edit_notes.setFixedHeight(100)
        layout.addRow("Note / Lavorazione:", self.edit_notes)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Crea Commessa")
        btn_save.setFixedHeight(36)
        btn_save.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_order)
        
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addRow("", btn_box)

    def save_order(self):
        c_id = self.combo_customer.currentData()
        machine = self.edit_machine.text().strip()
        serial = self.edit_serial.text().strip()
        notes = self.edit_notes.toPlainText().strip()

        if not machine:
            QMessageBox.warning(self, "Attenzione", "Inserisci il modello della macchina.")
            return

        try:
            self.controller.create_work_order(c_id, machine, serial, notes)
            QMessageBox.information(self, "Successo", "Commessa creata con successo!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile creare la commessa:\n{e}")


class WorkOrdersWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.setup_ui()
        self.load_work_orders()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header Bar
        top_layout = QHBoxLayout()
        title = QLabel("🛠️ Commesse & Lavorazioni Officina")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch()

        btn_new = QPushButton("+ Nuova Scheda Lavoro")
        btn_new.setFixedHeight(36)
        btn_new.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; font-size: 13px; padding: 0 15px; border-radius: 4px;")
        btn_new.clicked.connect(self.open_new_dialog)
        top_layout.addWidget(btn_new)

        top_layout.addSpacing(15)
        top_layout.addWidget(QLabel("Stato:"))
        self.combo_status = QComboBox()
        self.combo_status.setFixedHeight(36)
        self.combo_status.addItems(["Tutte", "APERTA", "IN_LAVORAZIONE", "ATTESA_RICAMBI", "PRONTA", "CHIUSA"])
        self.combo_status.currentTextChanged.connect(self.load_work_orders)
        top_layout.addWidget(self.combo_status)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca commessa o cliente...")
        self.search_input.setFixedWidth(240)
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self.load_work_orders)
        top_layout.addWidget(self.search_input)

        btn_refresh = QPushButton("Aggiorna")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self.load_work_orders)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        # Tabella Commesse
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "N. Commessa", "Data Apertura", "Cliente", "Macchinario", "Matricola", "Stato", "Note Lavorazione"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        self.lbl_count = QLabel("Caricamento commesse...")
        self.lbl_count.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.lbl_count)

    def load_work_orders(self):
        status = self.combo_status.currentText()
        query = self.search_input.text().strip()
        orders = self.controller.get_work_orders(status_filter=status, search_text=query)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(orders))

        status_colors = {
            "APERTA": "#1976D2",
            "IN_LAVORAZIONE": "#F57C00",
            "ATTESA_RICAMBI": "#7B1FA2",
            "PRONTA": "#388E3C",
            "CHIUSA": "#616161"
        }

        for i, wo in enumerate(orders):
            self.table.setItem(i, 0, SortableTableWidgetItem(wo.number))
            date_str = wo.date_opened.strftime("%d/%m/%Y") if wo.date_opened else "-"
            self.table.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=wo.date_opened or ""))
            self.table.setItem(i, 2, QTableWidgetItem(wo.customer.name if wo.customer else "-"))
            self.table.setItem(i, 3, QTableWidgetItem(wo.machine_model or "-"))
            self.table.setItem(i, 4, QTableWidgetItem(wo.machine_serial or "-"))

            # Stato colorato
            item_status = QTableWidgetItem(wo.status)
            color_hex = status_colors.get(wo.status, "#333333")
            item_status.setForeground(Qt.GlobalColor.white)
            item_status.setBackground(Qt.GlobalColor.transparent)
            self.table.setItem(i, 5, item_status)

            self.table.setItem(i, 6, QTableWidgetItem(wo.notes or "-"))

        self.table.setSortingEnabled(True)
        self.lbl_count.setText(f"Trovate {len(orders)} commesse.")

    def open_new_dialog(self):
        dlg = NewWorkOrderDialog(self.controller, self)
        if dlg.exec():
            self.load_work_orders()

    def refresh_data(self):
        self.load_work_orders()
