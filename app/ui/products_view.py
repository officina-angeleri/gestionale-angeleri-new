from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from app.utils.ui_utils import SortableTableWidgetItem

class ProductsWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.setup_ui()
        self.load_products()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Top bar
        top_layout = QHBoxLayout()
        title = QLabel("⚙️ Catalogo Ricambi & Magazzino Master")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch()

        top_layout.addWidget(QLabel("Categoria:"))
        self.combo_cat = QComboBox()
        self.combo_cat.setFixedHeight(36)
        self.combo_cat.setMinimumWidth(210)
        self.combo_cat.currentIndexChanged.connect(self._on_filter_changed)
        top_layout.addWidget(self.combo_cat)

        top_layout.addWidget(QLabel("Limite:"))
        self.combo_limit = QComboBox()
        self.combo_limit.setFixedHeight(36)
        self.combo_limit.addItem("Primi 300 articoli (Veloce)", 300)
        self.combo_limit.addItem("Primi 1.000 articoli", 1000)
        self.combo_limit.addItem("Tutti gli articoli", 0)
        self.combo_limit.currentIndexChanged.connect(self._on_filter_changed)
        top_layout.addWidget(self.combo_limit)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca codice o descrizione...")
        self.search_input.setFixedWidth(260)
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self._on_filter_changed)
        top_layout.addWidget(self.search_input)

        btn_refresh = QPushButton("🔄 Aggiorna")
        btn_refresh.setFixedHeight(36)
        btn_refresh.clicked.connect(self.refresh_data)
        top_layout.addWidget(btn_refresh)

        layout.addLayout(top_layout)

        # Tabella Catalogo
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Codice Master", "Descrizione Articolo", "Tipo", "Categoria", 
            "Costo STD", "Listino Vendita", "Codici Esploso / Vecchi", "Fornitori Collegati"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

        # Barra inferiore conteggi e azioni
        bottom_layout = QHBoxLayout()
        self.lbl_count = QLabel("Caricamento articoli...")
        self.lbl_count.setStyleSheet("color: #334155; font-size: 12px;")
        bottom_layout.addWidget(self.lbl_count, stretch=1)

        self.btn_load_all = QPushButton("Mostra tutti gli articoli")
        self.btn_load_all.setFixedHeight(28)
        self.btn_load_all.setVisible(False)
        self.btn_load_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_all.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #0369A1; }
        """)
        self.btn_load_all.clicked.connect(self._load_all_records)
        bottom_layout.addWidget(self.btn_load_all)

        layout.addLayout(bottom_layout)

        self.load_categories()

    def load_categories(self):
        """Carica dinamicamente tutte le categorie reali dal database con i rispettivi conteggi."""
        self.combo_cat.blockSignals(True)
        self.combo_cat.clear()
        
        try:
            cat_counts = self.controller.get_product_categories_with_counts()
            total_sum = sum(count for _, count in cat_counts)
            self.combo_cat.addItem(f"Tutte le categorie ({total_sum:,})", "Tutte")
            
            for cat_name, count in cat_counts:
                self.combo_cat.addItem(f"{cat_name} ({count:,})", cat_name)
        except Exception:
            self.combo_cat.addItem("Tutte", "Tutte")
            
        self.combo_cat.blockSignals(False)

    def _on_filter_changed(self):
        self.load_products()

    def _load_all_records(self):
        # Imposta limite su 'Tutti' (valore 0) e ricarica
        idx = self.combo_limit.findData(0)
        if idx >= 0:
            self.combo_limit.setCurrentIndex(idx)
        else:
            self.load_products(override_limit=0)

    def load_products(self, override_limit=None):
        cat = self.combo_cat.currentData() or "Tutte"
        query = self.search_input.text().strip()
        
        if override_limit is not None:
            limit = override_limit
        else:
            limit = self.combo_limit.currentData()
            if limit is None:
                limit = 300
        
        products, total_count = self.controller.get_products_catalog_with_count(
            category=cat, search_text=query, limit=limit
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(products))

        for i, prod in enumerate(products):
            self.table.setItem(i, 0, SortableTableWidgetItem(prod.code))
            self.table.setItem(i, 1, QTableWidgetItem(prod.name))
            self.table.setItem(i, 2, QTableWidgetItem(prod.type))
            self.table.setItem(i, 3, QTableWidgetItem(prod.category or "-"))
            
            cost_str = f"€ {prod.production_cost:.2f}" if prod.production_cost else "-"
            self.table.setItem(i, 4, SortableTableWidgetItem(cost_str, sort_value=prod.production_cost or 0.0))
            
            list_str = f"€ {prod.list_price:.2f}" if prod.list_price else "-"
            self.table.setItem(i, 5, SortableTableWidgetItem(list_str, sort_value=prod.list_price or 0.0))
            
            # Codici legacy
            leg_codes = [l.legacy_code for l in prod.legacy_codes]
            self.table.setItem(i, 6, QTableWidgetItem(", ".join(leg_codes) if leg_codes else "-"))

            # Codici fornitore
            supp_codes = [f"{sp.supplier_code}" for sp in prod.supplier_products]
            self.table.setItem(i, 7, QTableWidgetItem(", ".join(supp_codes) if supp_codes else "-"))

        self.table.setSortingEnabled(True)

        # Testo esplicativo trasparente
        loaded = len(products)
        cat_label = f" della categoria '{cat}'" if cat != "Tutte" else ""
        query_label = f" con ricerca '{query}'" if query else ""
        
        if loaded < total_count:
            self.lbl_count.setText(
                f"<b>Visualizzati i primi {loaded} su {total_count:,} articoli</b>{cat_label}{query_label} "
                f"(Limite di visualizzazione rapida attivo per garantire la massima velocità)."
            )
            self.btn_load_all.setText(f"📥 Mostra tutti i {total_count:,} articoli")
            self.btn_load_all.setVisible(True)
        else:
            self.lbl_count.setText(
                f"<b>Visualizzati tutti i {total_count:,} articoli</b>{cat_label}{query_label}."
            )
            self.btn_load_all.setVisible(False)

    def _on_cell_double_clicked(self, row, col):
        item = self.table.item(row, 0)
        if not item:
            return
        art_code = item.text().strip()
        if hasattr(self.main_window, 'article_search') and hasattr(self.main_window, 'switch_view'):
            self.main_window.switch_view(5) # Passa a Ricerca 360°
            self.main_window.article_search.search_input.setText(art_code)
            self.main_window.article_search.perform_search()

    def refresh_data(self):
        self.load_categories()
        self.load_products()
