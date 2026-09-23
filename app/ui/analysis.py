from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHBoxLayout, QLabel, QHeaderView, QPushButton, QDialog, QLineEdit, QScrollArea, QFrame,
                             QComboBox)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from app.utils.ui_utils import SortableTableWidgetItem
from app.controllers.analysis_engine import AnalysisEngine
import os
from datetime import datetime
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

class HistoryDialog(QDialog):
    def __init__(self, product, supplier, history_data):
        super().__init__()
        self.setWindowTitle(f"Storico: {product}")
        self.resize(700, 500)
        
        layout = QVBoxLayout()
        
        product_info = f"Codice Articolo: <b>{product}</b>"
        if history_data and history_data[0].get('CodiceCliente'):
            product_info += f"<br>Codice Cliente: <b>{history_data[0]['CodiceCliente']}</b>"
        product_info += f"<br>Fornitore: {supplier}"
        
        lbl_info = QLabel(product_info)
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_info)
        
        self.lbl_total_qty = QLabel("Totale Pezzi Acquistati: 0")
        self.lbl_total_qty.setStyleSheet("font-weight: bold; color: #1565C0;")
        layout.addWidget(self.lbl_total_qty)
        
        # Filtri Scroll Area
        self.filters_scroll = QScrollArea()
        self.filters_scroll.setWidgetResizable(True)
        self.filters_scroll.setFixedHeight(40)
        self.filters_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filters_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.filters_container = QWidget()
        self.filters_layout = QHBoxLayout(self.filters_container)
        self.filters_scroll.setWidget(self.filters_container)
        layout.addWidget(self.filters_scroll)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Data", "N. Fattura", "Descrizione", "Prezzo Unit.", "Variazione", "Q.tà", "File"])
        
        # Sincronizza Scroll
        self.table.horizontalScrollBar().valueChanged.connect(
            self.filters_scroll.horizontalScrollBar().setValue
        )
        
        # Interattività Header
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # Trova il massimo storico in questo set di dati
        max_all_time = max([r['Prezzo'] for r in history_data]) if history_data else 0
        
        self.setup_filters()
        self.populate_data(history_data, max_all_time)
        
        layout.addWidget(self.table)
        self.setLayout(layout)

    def setup_filters(self):
        self.filters = []
        self.filters_layout.setSpacing(0)
        self.filters_layout.setContentsMargins(0, 0, 0, 0)
        
        # Spacer per la colonna del vertical header (numeri riga)
        spacer = QWidget()
        spacer.setFixedWidth(self.table.verticalHeader().width() if self.table.verticalHeader().isVisible() else 0)
        self.filters_layout.addWidget(spacer)
        self.header_spacer = spacer
        
        for i in range(self.table.columnCount()):
            edit = QLineEdit()
            edit.setPlaceholderText(f"F...")
            edit.textChanged.connect(self.apply_filters)
            self.filters_layout.addWidget(edit)
            self.filters.append(edit)
            
        self.table.horizontalHeader().sectionResized.connect(self.sync_filters_layout)
        self.table.horizontalHeader().sectionMoved.connect(self.sync_filters_layout)
        self.sync_filters_layout()

    def sync_filters_layout(self):
        # Allinea lo spacer iniziale alla larghezza attuale del vertical header
        if self.table.verticalHeader().isVisible():
            self.header_spacer.setFixedWidth(self.table.verticalHeader().width())
        else:
            self.header_spacer.setFixedWidth(0)
            
        # Reordina i filtri nel layout in base alla posizione VISIVA delle colonne
        # Primo, rimuoviamo tutti (tranne lo spacer)
        for i in range(self.filters_layout.count() - 1, 0, -1):
            item = self.filters_layout.takeAt(i)
            # Non cancelliamo il widget, lo togliamo solo dal layout
            
        # Poi li riaggiungiamo nell'ordine visuale corretto
        header = self.table.horizontalHeader()
        for vi in range(self.table.columnCount()):
            li = header.logicalIndex(vi)
            width = self.table.columnWidth(li)
            self.filters[li].setFixedWidth(width)
            self.filters_layout.addWidget(self.filters[li])

    def apply_filters(self):
        for row in range(self.table.rowCount()):
            match = True
            for col in range(self.table.columnCount()):
                filter_text = self.filters[col].text().lower()
                if filter_text:
                    item = self.table.item(row, col)
                    if item and filter_text not in item.text().lower():
                        match = False
                        break
            self.table.setRowHidden(row, not match)

    def populate_data(self, history_data, max_all_time):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(history_data))
        for i, row in enumerate(history_data):
            date_val = row['Data']
            self.table.setItem(i, 0, SortableTableWidgetItem(str(date_val), sort_value=date_val))
            self.table.setItem(i, 1, QTableWidgetItem(str(row['Numero Fattura'])))
            self.table.setItem(i, 2, QTableWidgetItem(str(row['Descrizione'])))
            
            p_val = row['Prezzo']
            p_item = SortableTableWidgetItem(f"€ {p_val:.4f}", sort_value=p_val)
            v_item = SortableTableWidgetItem("", sort_value=0.0) # Default empty
            
            # Cerca il prezzo della fattura precedente (cronologicamente)
            prev_price = None
            for j in range(i + 1, len(history_data)):
                if history_data[j]['Numero Fattura'] != row['Numero Fattura']:
                    prev_price = history_data[j]['Prezzo']
                    break
            
            if prev_price is not None:
                curr_price = row['Prezzo']
                diff = curr_price - prev_price
                if abs(diff) > 0.0001:
                    v_item.setText(f"€ {diff:+.4f}")
                    v_item.sort_value = diff
                    if diff > 0:
                        p_item.setBackground(QColor("#FFCDD2")) # Red
                        v_item.setForeground(QColor("red"))
                    else:
                        p_item.setBackground(QColor("#C8E6C9")) # Green
                        v_item.setForeground(QColor("green"))
            
            # Highlight Picco
            if abs(row['Prezzo'] - max_all_time) < 0.0001 and p_item.background().color().name() == "#000000":
                 p_item.setBackground(QColor("#FFF9C4"))
                 p_item.setToolTip("Prezzo Massimo Storico")

            self.table.setItem(i, 3, p_item)
            self.table.setItem(i, 4, v_item)
            self.table.setItem(i, 5, SortableTableWidgetItem(str(row['Quantità']), sort_value=row['Quantità']))
            self.table.setItem(i, 6, QTableWidgetItem(os.path.basename(str(row['File']))))
            
        total_qty = sum([r['Quantità'] for r in history_data])
        self.lbl_total_qty.setText(f"Totale Pezzi Acquistati: {total_qty:.2f}")
            
        self.table.setSortingEnabled(True)
        self.apply_filters()
        self.sync_filters_layout() # Sincronizza dopo popolamento (importante se ResizeToContents)

class VisualReportDialog(QDialog):
    """Dialogo per mostrare un grafico temporale dell'andamento dei prezzi di un articolo."""
    def __init__(self, product, supplier, history_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Grafico Storico Prezzi: {product}")
        self.resize(850, 600)
        
        layout = QVBoxLayout(self)
        
        # Info header
        product_info = f"<h3>Andamento Prezzi Articolo</h3><b>Articolo/Codice:</b> {product}<br><b>Fornitore:</b> {supplier}"
        if history_data and history_data[0].get('CodiceCliente'):
            product_info += f" | <b>Cod. Cliente:</b> {history_data[0]['CodiceCliente']}"
        
        lbl_info = QLabel(product_info)
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        lbl_info.setStyleSheet("font-size: 13px; padding-bottom: 5px;")
        layout.addWidget(lbl_info)
        
        # Matplotlib Figure & Canvas
        self.figure = Figure(figsize=(8, 5.5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # Pulsante Chiudi
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.setFixedWidth(120)
        btn_close.setFixedHeight(36)
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        self.plot_history(history_data)

    def plot_history(self, history_data):
        if not history_data:
            return
            
        # Ordina cronologicamente
        sorted_history = sorted(history_data, key=lambda x: x['Data'])
        
        dates = []
        prices = []
        quantities = []
        
        for row in sorted_history:
            try:
                d = datetime.strptime(row['Data'], '%Y-%m-%d')
                dates.append(d)
                prices.append(row['Prezzo'])
                quantities.append(row['Quantità'])
            except Exception as e:
                print(f"Errore parsing riga storico: {e}")
                
        if not dates:
            return
            
        ax = self.figure.add_subplot(111)
        
        # Plot prezzi come linea con marcatori
        ax.plot(dates, prices, marker='o', markersize=6, color='#1976D2', linewidth=2.5, label='Prezzo Unitario (€)')
        
        # Annotazioni per ciascun punto
        for i, (date_val, price_val) in enumerate(zip(dates, prices)):
            qty = quantities[i]
            ax.annotate(f"€{price_val:.2f}\n(q.tà: {qty:.0f})", 
                        (date_val, price_val), 
                        textcoords="offset points", 
                        xytext=(0, 10), 
                        ha='center', 
                        fontsize=8, 
                        fontweight='bold',
                        bbox=dict(boxstyle="round,pad=0.3", fc="#E3F2FD", ec="#90CAF9", lw=0.7, alpha=0.9))
        
        # Linea della media
        avg_price = sum(prices) / len(prices)
        ax.axhline(avg_price, color='#D32F2F', linestyle='--', linewidth=1.5, label=f'Media: €{avg_price:.2f}')
        
        # Estetica assi
        ax.set_title("Storico Prezzi d'Acquisto nel Tempo", fontsize=13, fontweight='bold', pad=15)
        ax.set_xlabel("Data d'Acquisto", fontsize=10, labelpad=8)
        ax.set_ylabel("Prezzo Unitario (€)", fontsize=10, labelpad=8)
        
        # Formattazione asse X (Date)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.figure.autofmt_xdate()
        
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='best', frameon=True, facecolor='#ffffff', edgecolor='#cccccc')
        
        # Imposta margini corretti
        self.figure.tight_layout()
        self.canvas.draw()

class AnalysisWidget(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.engine = AnalysisEngine()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Analisi Trend Prezzi")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header_layout.addWidget(title)
        
        self.btn_chart = QPushButton("Mostra Grafico Prezzi")
        self.btn_chart.setEnabled(False)
        self.btn_chart.clicked.connect(self.show_visual_report)
        self.btn_chart.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(self.btn_chart)
        
        btn_refresh = QPushButton("Aggiorna Analisi")
        btn_refresh.clicked.connect(self.refresh_data)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(btn_refresh)
        
        layout.addLayout(header_layout)
        
        # Hints
        lbl_hint = QLabel("Doppio click su una riga per lo storico dettagliato. Seleziona una riga e premi 'Mostra Grafico Prezzi' per il report visivo.")
        lbl_hint.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(lbl_hint)
        
        # Filtri Globali
        global_filters_layout = QHBoxLayout()
        
        global_filters_layout.addWidget(QLabel("Fornitore:"))
        self.filter_supplier_global = QComboBox()
        self.filter_supplier_global.setFixedHeight(36)
        self.filter_supplier_global.setMinimumWidth(220)
        self.filter_supplier_global.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_supplier_global.currentTextChanged.connect(self.apply_filters)
        global_filters_layout.addWidget(self.filter_supplier_global)
        
        global_filters_layout.addSpacing(20)
        
        global_filters_layout.addWidget(QLabel("Codice Articolo:"))
        self.filter_product_global = QLineEdit()
        self.filter_product_global.setPlaceholderText("Cerca codice...")
        self.filter_product_global.setClearButtonEnabled(True)
        self.filter_product_global.textChanged.connect(self.apply_filters)
        global_filters_layout.addWidget(self.filter_product_global)
        
        layout.addLayout(global_filters_layout)
        
        # Filtri Scroll Area
        self.filters_scroll = QScrollArea()
        self.filters_scroll.setWidgetResizable(True)
        self.filters_scroll.setFixedHeight(40)
        self.filters_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filters_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.filters_container = QWidget()
        self.filters_layout = QHBoxLayout(self.filters_container)
        self.filters_scroll.setWidget(self.filters_container)
        layout.addWidget(self.filters_scroll)
        
        # Table
        self.table = QTableWidget()
        
        # Sincronizza Scroll
        self.table.horizontalScrollBar().valueChanged.connect(
            self.filters_scroll.horizontalScrollBar().setValue
        )
        self.table.setColumnCount(13) 
        self.table.setHorizontalHeaderLabels([
            "Codice Articolo", "Cod. Art. Cliente", "Descrizione", "Fornitore", "Ultimo Prezzo", "Min", "Max", "Media", "Var vs Max %", "Data", "Variazione", "Var. %", "Stato"
        ])
        
        # Interattività Header
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Setup initial stretch but allow manual resize
        for i in range(self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self.show_history)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # Read only
        layout.addWidget(self.table)
        
        self.setLayout(layout)
        self.setup_filters()
        
    def setup_filters(self):
        self.filters = []
        self.filters_layout.setSpacing(0)
        self.filters_layout.setContentsMargins(0, 0, 0, 0)
        
        # Spacer per vertical header
        spacer = QWidget()
        spacer.setFixedWidth(self.table.verticalHeader().width() if self.table.verticalHeader().isVisible() else 0)
        self.filters_layout.addWidget(spacer)
        self.header_spacer = spacer

        for i in range(self.table.columnCount()):
            edit = QLineEdit()
            edit.setPlaceholderText("Filtra...")
            edit.textChanged.connect(self.apply_filters)
            self.filters_layout.addWidget(edit)
            self.filters.append(edit)
            
        self.table.horizontalHeader().sectionResized.connect(self.sync_filters_layout)
        self.table.horizontalHeader().sectionMoved.connect(self.sync_filters_layout)
        self.sync_filters_layout()

    def sync_filters_layout(self):
        if self.table.verticalHeader().isVisible():
            self.header_spacer.setFixedWidth(self.table.verticalHeader().width())
        else:
            self.header_spacer.setFixedWidth(0)
            
        # Rimuovi filtri esistenti (tranne spacer)
        for i in range(self.filters_layout.count() - 1, 0, -1):
            self.filters_layout.takeAt(i)
            
        header = self.table.horizontalHeader()
        for vi in range(self.table.columnCount()):
            li = header.logicalIndex(vi)
            width = self.table.columnWidth(li)
            self.filters[li].setFixedWidth(width)
            self.filters_layout.addWidget(self.filters[li])

    def apply_filters(self):
        # Valori filtri globali
        supp_glob = self.filter_supplier_global.currentText().lower()
        if supp_glob == "tutti i fornitori":
            supp_glob = ""
        prod_glob = self.filter_product_global.text().lower()
        
        for row in range(self.table.rowCount()):
            match = True
            
            # 1. Controllo Filtro Globale Fornitore (Colonna 3)
            if supp_glob:
                item = self.table.item(row, 3)
                if not item or supp_glob not in item.text().lower():
                    match = False
            
            # 2. Controllo Filtro Globale Prodotto (Colonna 0 o Colonna 1)
            if match and prod_glob:
                item_code = self.table.item(row, 0)
                item_cust = self.table.item(row, 1)
                code_txt = item_code.text().lower() if item_code else ""
                cust_txt = item_cust.text().lower() if item_cust else ""
                if prod_glob not in code_txt and prod_glob not in cust_txt:
                    match = False
            
            # 3. Controllo Filtri di Colonna
            if match:
                for col in range(self.table.columnCount()):
                    filter_text = self.filters[col].text().lower()
                    if filter_text:
                        item = self.table.item(row, col)
                        if item and filter_text not in item.text().lower():
                            match = False
                            break
                            
            self.table.setRowHidden(row, not match)
            
    def on_selection_changed(self):
        # Abilita il pulsante se c'è almeno una riga selezionata
        selected = self.table.selectedItems()
        self.btn_chart.setEnabled(len(selected) > 0)
            
    def show_visual_report(self):
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            return
        row = selected_ranges[0].topRow()
        
        # Prendi i dati della riga selezionata (Colonna 0: Prodotto, Colonna 3: Fornitore)
        product_item = self.table.item(row, 0)
        supplier_item = self.table.item(row, 3)
        
        if product_item and supplier_item:
            product_name = product_item.text()
            supplier_name = supplier_item.text()
            
            history = self.engine.get_product_history(product_name, supplier_name)
            
            dlg = VisualReportDialog(product_name, supplier_name, history, parent=self)
            dlg.exec()
            
    def show_history(self, row, col):
        product_name = self.table.item(row, 0).text()
        # Fornitore è ora alla colonna 3
        supplier_name = self.table.item(row, 3).text()
        
        history = self.engine.get_product_history(product_name, supplier_name)
        
        dlg = HistoryDialog(product_name, supplier_name, history)
        dlg.exec()
        
    def refresh_data(self):
        self.table.setSortingEnabled(False)
        data = self.engine.get_price_trends()
        
        # Ordina per variazione percentuale assoluta decrescente
        data = sorted(data, key=lambda x: abs(x['Var. %']), reverse=True)
        
        # Popola il combobox dei fornitori
        suppliers = sorted(list(set(row_data['Fornitore'] for row_data in data)))
        
        self.filter_supplier_global.blockSignals(True)
        current_selection = self.filter_supplier_global.currentText()
        self.filter_supplier_global.clear()
        self.filter_supplier_global.addItem("Tutti i fornitori")
        self.filter_supplier_global.addItems(suppliers)
        
        idx = self.filter_supplier_global.findText(current_selection)
        if idx >= 0:
            self.filter_supplier_global.setCurrentIndex(idx)
        else:
            self.filter_supplier_global.setCurrentIndex(0)
        self.filter_supplier_global.blockSignals(False)
        
        self.table.setRowCount(0)
        
        for row_data in data:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            
            # Create items - Use NumericTableWidgetItem for numeric columns
            items = [
                QTableWidgetItem(str(row_data['Prodotto'])),
                QTableWidgetItem(str(row_data['CodiceCliente'] or "")),
                QTableWidgetItem(str(row_data['Descrizione'])),
                QTableWidgetItem(str(row_data['Fornitore'])),
                SortableTableWidgetItem(f"€ {row_data['Ultimo Prezzo']:.2f}", sort_value=row_data['Ultimo Prezzo']),
                SortableTableWidgetItem(f"€ {row_data['Min']:.2f}", sort_value=row_data['Min']),
                SortableTableWidgetItem(f"€ {row_data['Max']:.2f}", sort_value=row_data['Max']),
                SortableTableWidgetItem(f"€ {row_data['Media']:.2f}", sort_value=row_data['Media']),
                SortableTableWidgetItem(f"{row_data['Var vs Max %']:.2f}%", sort_value=row_data['Var vs Max %']),
                SortableTableWidgetItem(str(row_data['Data Ultimo']), sort_value=row_data['Data Ultimo']),
                SortableTableWidgetItem(f"€ {row_data['Var. Ass.']:.2f}", sort_value=row_data['Var. Ass.']),
                SortableTableWidgetItem(f"{row_data['Var. %']:.2f}%", sort_value=row_data['Var. %']),
                QTableWidgetItem(str(row_data['Stato']))
            ]
            
            # Highlight Var vs Max if negative (significant saving)
            if row_data['Var vs Max %'] < -10:
                items[8].setForeground(QColor("green"))
                items[8].setFont(QFont("Arial", weight=QFont.Weight.Bold))

            # Parsing logic for color and font for recent trend
            status = row_data['Stato']
            color = None
            if status in ["Aumento", "Prezzo Alto"]:
                color = QColor("#FFCDD2") # Red lighten-4
                if row_data['Var. Ass.'] > 0:
                    items[10].setForeground(QColor("red"))
            elif status in ["Diminuzione", "Prezzo Basso"]:
                color = QColor("#C8E6C9") # Green lighten-4
                if row_data['Var. Ass.'] < 0:
                    items[10].setForeground(QColor("green"))
            
            for i, item in enumerate(items):
                if color:
                    item.setBackground(color)
                self.table.setItem(row_idx, i, item)
                
        self.table.setSortingEnabled(True)
        self.apply_filters()
        self.sync_filters_layout()
