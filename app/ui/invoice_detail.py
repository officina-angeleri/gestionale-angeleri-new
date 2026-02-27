from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QPushButton, QGroupBox, QFormLayout)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from app.utils.ui_utils import SortableTableWidgetItem
from app.database import get_db_session, Invoice, InvoiceItem, Supplier


class InvoiceDetailDialog(QDialog):
    """Dialogo dettaglio fattura: testata + righe articolo."""

    def __init__(self, invoice_id: int, parent=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Dettaglio Fattura")
        self.resize(900, 580)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Testata ──
        self.grp_header = QGroupBox("Dati Fattura")
        form = QFormLayout(self.grp_header)
        form.setSpacing(6)

        self.lbl_numero    = QLabel("-")
        self.lbl_data      = QLabel("-")
        self.lbl_fornitore = QLabel("-")
        self.lbl_totale    = QLabel("-")

        for label, widget in [
            ("Numero:",    self.lbl_numero),
            ("Data:",      self.lbl_data),
            ("Fornitore:", self.lbl_fornitore),
            ("Totale:",    self.lbl_totale),
        ]:
            lkey = QLabel(label)
            lkey.setStyleSheet("font-weight: bold; color: #1565C0;")
            widget.setStyleSheet("font-size: 13px;")
            form.addRow(lkey, widget)

        self.lbl_totale.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #2E7D32;")
        layout.addWidget(self.grp_header)

        # ── Tabella righe ──
        lbl_righe = QLabel("Righe Articolo")
        lbl_righe.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_righe)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Codice", "Descrizione", "Q.tà", "Prezzo Unit.", "Totale Riga"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        # ── Footer ──
        footer = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #666; font-style: italic;")
        footer.addWidget(self.lbl_count)
        footer.addStretch()

        btn_close = QPushButton("Chiudi")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def load_data(self):
        session = get_db_session()
        try:
            invoice = session.get(Invoice, self.invoice_id)
            if not invoice:
                self.setWindowTitle("Fattura non trovata")
                return

            self.setWindowTitle(
                f"Fattura n. {invoice.number}  —  {invoice.supplier.name}")
            self.lbl_numero.setText(str(invoice.number))
            self.lbl_data.setText(
                invoice.date.strftime("%d/%m/%Y") if invoice.date else "-")
            self.lbl_fornitore.setText(invoice.supplier.name)
            self.lbl_totale.setText(f"€ {invoice.total_amount:,.2f}")

            items = session.query(InvoiceItem).filter_by(
                invoice_id=self.invoice_id).all()

            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(items))

            for i, item in enumerate(items):
                self.table.setItem(i, 0,
                    QTableWidgetItem(item.code or "-"))
                self.table.setItem(i, 1,
                    QTableWidgetItem(item.description or "-"))
                self.table.setItem(i, 2,
                    SortableTableWidgetItem(
                        f"{item.quantity:.2f}", sort_value=item.quantity))
                self.table.setItem(i, 3,
                    SortableTableWidgetItem(
                        f"€ {item.unit_price:.4f}", sort_value=item.unit_price))

                tot_item = SortableTableWidgetItem(
                    f"€ {item.total_price:.2f}", sort_value=item.total_price)
                tot_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, 4, tot_item)

            self.table.setSortingEnabled(True)
            self.lbl_count.setText(
                f"{len(items)} righe — File: {invoice.file_path or '-'}")

        except Exception as e:
            self.lbl_numero.setText(f"Errore: {e}")
        finally:
            session.close()
