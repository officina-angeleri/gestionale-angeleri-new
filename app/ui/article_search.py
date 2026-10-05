from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QLabel, QCheckBox, QComboBox, QTabWidget, QGroupBox, QGridLayout,
                             QInputDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
import re
from app.utils.ui_utils import SortableTableWidgetItem
from app.database import get_db_session, Supplier, Customer

class ArticleSearchWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.active_search_steps = []
        self.setup_ui()
        self._populate_filters()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Titolo & Sottotitolo
        title_layout = QHBoxLayout()
        title = QLabel("Ricerca Ricambi & Scheda 360°")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        lbl_info = QLabel("PostgreSQL su Synology DS920+ attivo")
        lbl_info.setStyleSheet("color: #2E7D32; font-weight: bold; background-color: #E8F5E9; padding: 4px 10px; border-radius: 4px;")
        title_layout.addWidget(lbl_info)
        layout.addLayout(title_layout)

        # Search bar con Tasto Vocale e Cerca
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca per codice master (es. A850-0050), codice vecchio (es. 3150-12), fornitore o testo...")
        self.search_input.setFixedHeight(42)
        self.search_input.setStyleSheet("font-size: 15px; padding-left: 12px; border: 1px solid #1976D2; border-radius: 4px;")
        self.search_input.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        
        # Tasto Ricerca Vocale
        self.btn_voice = QPushButton("🎙️ VOCE")
        self.btn_voice.setFixedHeight(42)
        self.btn_voice.setFixedWidth(100)
        self.btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice.setStyleSheet("background-color: #E65100; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_voice.clicked.connect(self.handle_voice_search)
        search_layout.addWidget(self.btn_voice)

        # Tasto Cerca Standard
        self.btn_search = QPushButton("🔍 CERCA")
        self.btn_search.setFixedHeight(42)
        self.btn_search.setFixedWidth(110)
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; font-size: 14px; border-radius: 4px;")
        self.btn_search.clicked.connect(self.perform_search)
        search_layout.addWidget(self.btn_search)
        layout.addLayout(search_layout)
        
        # Filtri e Opzioni
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Fornitore:"))
        self.combo_supplier = QComboBox()
        self.combo_supplier.setFixedHeight(32)
        self.combo_supplier.setMinimumWidth(200)
        options_layout.addWidget(self.combo_supplier)

        options_layout.addSpacing(15)
        self.cb_code = QCheckBox("Codice articolo")
        self.cb_desc = QCheckBox("Descrizione articolo")
        self.cb_code.setChecked(True)
        self.cb_desc.setChecked(True)
        options_layout.addWidget(self.cb_code)
        options_layout.addWidget(self.cb_desc)
        
        options_layout.addSpacing(15)
        self.cb_group_invoices = QCheckBox("Raggruppa per fattura (1 riga per fattura)")
        self.cb_group_invoices.setToolTip("Se attivo, mostra una sola riga per fattura con il totale e l'elenco riassuntivo degli articoli contenuti, evitando ripetizioni.")
        self.cb_group_invoices.stateChanged.connect(self._on_grouping_changed)
        options_layout.addWidget(self.cb_group_invoices)

        options_layout.addSpacing(15)
        self.cb_incremental = QCheckBox("Ricerca incrementale")
        self.cb_incremental.stateChanged.connect(self.update_mode_label)
        options_layout.addWidget(self.cb_incremental)
        
        self.lbl_mode = QLabel("Modalità: Nuova ricerca")
        self.lbl_mode.setStyleSheet("color: #666; font-style: italic;")
        options_layout.addWidget(self.lbl_mode)
        
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Box Risultati Intermedi Articoli Catalogo Corrispondenti
        self.box_matching_products = QGroupBox("📋 Articoli Corrispondenti nel Catalogo")
        self.box_matching_products.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #1976D2; border-radius: 6px; margin-top: 6px; padding: 10px; background-color: #F0F4F8; }"
        )
        box_prod_layout = QVBoxLayout(self.box_matching_products)
        box_prod_layout.setContentsMargins(8, 8, 8, 8)
        box_prod_layout.setSpacing(6)

        # Header box: titolo/guida + campo filtraggio rapido + toggle
        prod_hdr_layout = QHBoxLayout()
        self.lbl_matching_products_title = QLabel("Seleziona l'articolo desiderato per visualizzarne la scheda e lo storico:")
        self.lbl_matching_products_title.setStyleSheet("font-weight: bold; color: #0D47A1; font-size: 13px;")
        prod_hdr_layout.addWidget(self.lbl_matching_products_title)
        prod_hdr_layout.addStretch()

        self.input_filter_matching = QLineEdit()
        self.input_filter_matching.setPlaceholderText("🔍 Filtra tra gli articoli trovati...")
        self.input_filter_matching.setFixedWidth(240)
        self.input_filter_matching.setFixedHeight(28)
        self.input_filter_matching.setStyleSheet("padding-left: 8px; border: 1px solid #90CAF9; border-radius: 4px; background: white;")
        self.input_filter_matching.textChanged.connect(self._filter_matching_products_table)
        prod_hdr_layout.addWidget(self.input_filter_matching)

        self.btn_toggle_matching = QPushButton("Comprimi ▲")
        self.btn_toggle_matching.setFixedHeight(28)
        self.btn_toggle_matching.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_matching.setStyleSheet("font-size: 11px; padding: 2px 10px; background: white; border: 1px solid #90CAF9; border-radius: 4px;")
        self.btn_toggle_matching.clicked.connect(self._toggle_matching_products)
        prod_hdr_layout.addWidget(self.btn_toggle_matching)

        box_prod_layout.addLayout(prod_hdr_layout)

        # Tabella Articoli Trovati
        self.table_matching_products = QTableWidget()
        self.table_matching_products.setColumnCount(7)
        self.table_matching_products.setHorizontalHeaderLabels([
            "Codice Articolo", "Descrizione", "Tipo / Categoria", "Costo STD", "Listino", "Disegno / B-Kode", "Codici Vecchi / Esploso"
        ])
        h_match = self.table_matching_products.horizontalHeader()
        h_match.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_match.setStretchLastSection(True)
        self.table_matching_products.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_matching_products.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_matching_products.setSortingEnabled(True)
        self.table_matching_products.setMinimumHeight(140)
        self.table_matching_products.setToolTip("Fai clic su un articolo per visualizzarne la Scheda 360°, lo storico vendite e gli acquisti")
        self.table_matching_products.itemSelectionChanged.connect(self._on_matching_product_selected)
        self.table_matching_products.cellClicked.connect(lambda r, c: self._on_matching_product_selected())
        box_prod_layout.addWidget(self.table_matching_products)

        self.box_matching_products.setVisible(False)

        # Scheda Riepilogo 360° Articolo (Box espandibile)
        self.box_360 = QGroupBox("Scheda Master Articolo & Equivalenze (360°)")
        self.box_360.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #B0BEC5; border-radius: 6px; margin-top: 10px; padding: 10px; background-color: #FAFAFA; }")
        self.box_360_layout = QGridLayout(self.box_360)
        
        self.lbl_art_master = QLabel("Codice: -")
        self.lbl_art_master.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_art_desc = QLabel("Descrizione: -")
        self.lbl_art_cat = QLabel("Categoria: -")
        self.lbl_art_cost = QLabel("Costo STD: -")
        self.lbl_art_list = QLabel("Listino Vendita: -")
        self.lbl_art_legacy = QLabel("Codici Esploso / Vecchi: -")
        self.lbl_art_legacy.setStyleSheet("color: #C2185B; font-weight: bold;")
        self.lbl_art_supp = QLabel("Codici Fornitore: -")
        self.lbl_art_supp.setStyleSheet("color: #0288D1; font-weight: bold;")

        self.box_360_layout.addWidget(self.lbl_art_master, 0, 0)
        self.box_360_layout.addWidget(self.lbl_art_cat, 0, 1)
        self.box_360_layout.addWidget(self.lbl_art_cost, 0, 2)
        self.box_360_layout.addWidget(self.lbl_art_list, 0, 3)
        self.box_360_layout.addWidget(self.lbl_art_desc, 1, 0, 1, 4)
        self.box_360_layout.addWidget(self.lbl_art_legacy, 2, 0, 1, 2)
        self.box_360_layout.addWidget(self.lbl_art_supp, 2, 2, 1, 2)

        # Riga 3: Listini Ufficiali B-Kode (Acquisto / Vendita)
        self.lbl_art_price_lists = QLabel("Listini B-Kode: In attesa selezione...")
        self.lbl_art_price_lists.setStyleSheet("color: #E65100; font-weight: bold;")
        self.box_360_layout.addWidget(self.lbl_art_price_lists, 3, 0, 1, 4)

        # Riga 4: Esplosi Macchine collegati & Apertura diretta PDF
        lbl_diag_title = QLabel("📖 Esplosi Macchine:")
        lbl_diag_title.setStyleSheet("color: #2E7D32; font-weight: bold;")
        self.box_360_layout.addWidget(lbl_diag_title, 4, 0)
        
        self.widget_diagrams_container = QWidget()
        self.layout_diagrams_btns = QHBoxLayout(self.widget_diagrams_container)
        self.layout_diagrams_btns.setContentsMargins(0, 0, 0, 0)
        self.layout_diagrams_btns.setSpacing(8)
        self.box_360_layout.addWidget(self.widget_diagrams_container, 4, 1, 1, 3)

        # Riga 5: Dati Produzione / Conversione / Disegno B-Kode
        self.lbl_art_bkode = QLabel("Produzione & Conversione B-Kode: -")
        self.lbl_art_bkode.setStyleSheet("color: #4527A0; font-weight: bold;")
        self.box_360_layout.addWidget(self.lbl_art_bkode, 5, 0, 1, 4)
        
        self.box_360.setVisible(False) # Visibile solo quando c'è un riscontro

        # Tabs Risultati: Acquisti Fornitori vs Vendite Clienti vs Distinta Base / Produzione
        self.tabs = QTabWidget()
        
        # TAB 1: ACQUISTI FORNITORI
        self.tab_purchases = QWidget()
        tab_p_layout = QVBoxLayout(self.tab_purchases)
        self.table_purchases = QTableWidget()
        self.table_purchases.setColumnCount(9)
        self.table_purchases.setHorizontalHeaderLabels([
            "Fattura", "Data", "Fornitore", "Cod. Fornitore", "Cod. Cliente", 
            "Descrizione", "Q.tà", "Prezzo Acquisto", "Totale"
        ])
        header_p = self.table_purchases.horizontalHeader()
        header_p.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_p.setStretchLastSection(True)
        self.table_purchases.setSortingEnabled(True)
        self.table_purchases.cellDoubleClicked.connect(self.handle_double_click_purchase)
        tab_p_layout.addWidget(self.table_purchases)
        self.tabs.addTab(self.tab_purchases, "Storico Acquisti Fornitori")

        # TAB 2: VENDITE CLIENTI
        self.tab_sales = QWidget()
        tab_s_layout = QVBoxLayout(self.tab_sales)
        self.table_sales = QTableWidget()
        self.table_sales.setColumnCount(9)
        self.table_sales.setHorizontalHeaderLabels([
            "Fattura", "Data", "Cliente", "Cod. Articolo", "Descrizione", 
            "U.M.", "Q.tà", "Prezzo Vendita", "Sconto %"
        ])
        header_s = self.table_sales.horizontalHeader()
        header_s.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_s.setStretchLastSection(True)
        self.table_sales.setSortingEnabled(True)
        self.table_sales.setToolTip("Fai doppio click su una riga per aprire la fattura originale completa di tutti i dettagli")
        self.table_sales.cellDoubleClicked.connect(self.handle_double_click_sales)
        tab_s_layout.addWidget(self.table_sales)
        self.tabs.addTab(self.tab_sales, "Storico Vendite Clienti (2019-2026)")

        # TAB 3: PRODUZIONE & DISTINTA BASE (BOM) & CICLO LAVORAZIONI
        self.tab_production = QWidget()
        tab_prod_layout = QVBoxLayout(self.tab_production)

        # Sezione Calcolatore Taglio Materiale (per articoli con fattore di conversione)
        self.box_calc_material = QGroupBox("📏 Calcolatore Taglio Materiale Grezzo (Conversione Lunghezza ➔ Peso)")
        self.box_calc_material.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #90CAF9; border-radius: 6px; margin-top: 5px; padding: 10px; background-color: #E3F2FD; }"
        )
        calc_layout = QHBoxLayout(self.box_calc_material)
        calc_layout.addWidget(QLabel("Lunghezza spezzone (mm):"))
        self.input_cut_len = QLineEdit("200")
        self.input_cut_len.setFixedWidth(90)
        self.input_cut_len.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px; background-color: white; border: 1px solid #1976D2; border-radius: 3px;")
        calc_layout.addWidget(self.input_cut_len)

        self.btn_calc_cut = QPushButton("Calcola Costo Spezzone")
        self.btn_calc_cut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_calc_cut.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        self.btn_calc_cut.clicked.connect(self._on_recalculate_cut)
        calc_layout.addWidget(self.btn_calc_cut)

        self.lbl_calc_result = QLabel("")
        self.lbl_calc_result.setStyleSheet("font-weight: bold; color: #0D47A1; font-size: 13px; margin-left: 15px;")
        calc_layout.addWidget(self.lbl_calc_result)
        calc_layout.addStretch()
        tab_prod_layout.addWidget(self.box_calc_material)

        # Sezione Distinta Materiali (BOM)
        lbl_bom_title = QLabel("🔩 Distinta Componenti & Materiali (BOM):")
        lbl_bom_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        tab_prod_layout.addWidget(lbl_bom_title)

        self.table_bom = QTableWidget()
        self.table_bom.setColumnCount(7)
        self.table_bom.setHorizontalHeaderLabels([
            "Riga", "Cod. Componente", "Descrizione", "U.M.", "Q.tà", "Costo Unitario", "Totale Materiale"
        ])
        header_bom = self.table_bom.horizontalHeader()
        header_bom.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_bom.setStretchLastSection(True)
        self.table_bom.setSortingEnabled(True)
        tab_prod_layout.addWidget(self.table_bom)

        # Sezione Ciclo Lavorazioni (Routing)
        lbl_routing_title = QLabel("⚙️ Ciclo di Lavorazione & Fasi Macchina:")
        lbl_routing_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        tab_prod_layout.addWidget(lbl_routing_title)

        self.table_routing = QTableWidget()
        self.table_routing.setColumnCount(7)
        self.table_routing.setHorizontalHeaderLabels([
            "Seq", "Cod. Fase", "Descrizione Lavorazione", "Ore Attrezzo", "Ore Macchina", "Tariffa €/h", "Totale Fase"
        ])
        header_rout = self.table_routing.horizontalHeader()
        header_rout.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_rout.setStretchLastSection(True)
        self.table_routing.setSortingEnabled(True)
        tab_prod_layout.addWidget(self.table_routing)

        # Strip Riepilogo Costi Produzione
        self.lbl_prod_cost_summary = QLabel("Seleziona o cerca un articolo per visualizzare i costi di produzione.")
        self.lbl_prod_cost_summary.setStyleSheet(
            "background-color: #263238; color: #ECEFF1; font-weight: bold; font-size: 13px; padding: 8px 12px; border-radius: 4px;"
        )
        self.tabs.addTab(self.tab_production, "Distinta Base & Lavorazioni (Produzione)")

        # TAB 4: LISTINI UFFICIALI B-KODE (Acquisti & Vendite)
        self.tab_pricelists = QWidget()
        tab_pl_layout = QVBoxLayout(self.tab_pricelists)
        
        lbl_p_pl = QLabel("🏷️ Listini di Acquisto Fornitori:")
        lbl_p_pl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        tab_pl_layout.addWidget(lbl_p_pl)
        
        self.table_purchase_prices = QTableWidget()
        self.table_purchase_prices.setColumnCount(9)
        self.table_purchase_prices.setHorizontalHeaderLabels([
            "Cod. Listino", "Descrizione Listino", "Fornitore", "U.M.",
            "Prezzo Base", "Sc. 1 %", "Sc. 2 %", "Prezzo Netto", "Validità"
        ])
        header_pp = self.table_purchase_prices.horizontalHeader()
        header_pp.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_pp.setStretchLastSection(True)
        self.table_purchase_prices.setSortingEnabled(True)
        tab_pl_layout.addWidget(self.table_purchase_prices)
        
        lbl_s_pl = QLabel("💰 Listini di Vendita Clienti:")
        lbl_s_pl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        tab_pl_layout.addWidget(lbl_s_pl)
        
        self.table_sales_prices = QTableWidget()
        self.table_sales_prices.setColumnCount(8)
        self.table_sales_prices.setHorizontalHeaderLabels([
            "Cod. Listino", "Descrizione Listino", "Cliente / Destinatario", "U.M.",
            "Prezzo Base", "Sconto %", "Prezzo Netto", "Validità"
        ])
        header_sp = self.table_sales_prices.horizontalHeader()
        header_sp.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_sp.setStretchLastSection(True)
        self.table_sales_prices.setSortingEnabled(True)
        tab_pl_layout.addWidget(self.table_sales_prices)
        
        self.tabs.addTab(self.tab_pricelists, "Listini Ufficiali (Acquisto / Vendita)")

        # Splitter Verticale Regolabile: consente all'utente di ridimensionare a piacere
        # l'altezza della lista articoli trovati rispetto ai dettagli/storico in basso
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background-color: #B0BEC5;
                height: 7px;
                margin: 2px 0px;
                border-radius: 3px;
            }
            QSplitter::handle:vertical:hover {
                background-color: #1976D2;
            }
        """)
        self.main_splitter.setToolTip("Trascina questo separatore per regolare l'altezza dell'elenco risultati")

        # Pannello superiore: Elenco Articoli Trovati
        self.main_splitter.addWidget(self.box_matching_products)

        # Pannello inferiore: Contenitore per Scheda 360 e Tab Storico
        self.bottom_container = QWidget()
        bottom_layout = QVBoxLayout(self.bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(6)
        bottom_layout.addWidget(self.box_360)
        bottom_layout.addWidget(self.tabs)

        self.main_splitter.addWidget(self.bottom_container)

        # Dimensioni iniziali generose: 300px per la lista articoli, 500px per lo storico
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([300, 500])

        layout.addWidget(self.main_splitter)
        
        # Status Bar interna
        self.status_label = QLabel("Pronto per la ricerca.")
        self.status_label.setStyleSheet("color: #666; font-size: 13px;")
        layout.addWidget(self.status_label)

    def _populate_filters(self):
        session = get_db_session()
        try:
            suppliers = session.query(Supplier.name).order_by(Supplier.name).all()
        except Exception:
            suppliers = []
        finally:
            session.close()
            
        self.combo_supplier.clear()
        self.combo_supplier.addItem("Tutti i fornitori", userData=None)
        for (name,) in suppliers:
            self.combo_supplier.addItem(name, userData=name)

    def update_mode_label(self):
        if self.cb_incremental.isChecked():
            self.lbl_mode.setText("Modalità: Ricerca incrementale")
            self.lbl_mode.setStyleSheet("color: #1565C0; font-weight: bold;")
        else:
            self.lbl_mode.setText("Modalità: Nuova ricerca")
            self.lbl_mode.setStyleSheet("color: #666; font-style: italic;")
            self.active_search_steps = []

    def handle_voice_search(self):
        """Attiva il microfono di sistema con finestra 'In ascolto' e trascrive l'audio."""
        from app.utils.voice_service import VoiceListeningDialog
        dlg = VoiceListeningDialog(self)
        if dlg.exec() and dlg.recognized_text:
            self.search_input.setText(dlg.recognized_text)
            self.perform_search()

    def perform_search(self):
        text = self.search_input.text().strip()
        if not text:
            self.table_purchases.setRowCount(0)
            self.table_sales.setRowCount(0)
            self.table_bom.setRowCount(0)
            self.table_routing.setRowCount(0)
            self.box_360.setVisible(False)
            self.box_matching_products.setVisible(False)
            self.active_search_steps = []
            return

        search_code = self.cb_code.isChecked()
        search_desc = self.cb_desc.isChecked()
        if not search_code and not search_desc:
            search_code = search_desc = True

        supplier_filter = self.combo_supplier.currentData()

        # 1. Cerca gli articoli corrispondenti nel catalogo prodotti
        matching_prods = self.controller.search_matching_products(
            text, supplier_name=supplier_filter, search_code=search_code, search_desc=search_desc
        )

        if len(matching_prods) > 1:
            # Mostra la lista degli articoli corrispondenti affinché l'utente possa selezionare l'articolo desiderato
            self.display_matching_products(matching_prods, text)
            self.box_360.setVisible(False)
            self.table_purchases.setRowCount(0)
            self.table_sales.setRowCount(0)
            self.table_bom.setRowCount(0)
            self.table_routing.setRowCount(0)
            self.lbl_prod_cost_summary.setText("Fai clic su un articolo della lista sopra per visualizzare distinta, lavorazioni e storico vendite/acquisti.")
            self.status_label.setText(
                f"Trovati {len(matching_prods)} articoli corrispondenti a '{text}'. Clicca su un articolo per aprire la scheda dedicata."
            )
            return
        elif len(matching_prods) == 1:
            # Trovato esattamente 1 articolo corrispondente:
            self.display_matching_products(matching_prods, text)
            self.load_product_detail(matching_prods[0].code)
            return
        else:
            # Nessun articolo a catalogo trovato per il testo:
            # Cerca direttamente nelle righe fatture (fallback)
            self.box_matching_products.setVisible(False)
            self.box_360.setVisible(False)
            self._perform_fallback_invoice_search(text, supplier_filter, search_code, search_desc)

    def display_matching_products(self, products, query_text):
        self.lbl_matching_products_title.setText(
            f"📋 Trovati {len(products)} articoli per '{query_text}'. Clicca su un articolo per visualizzarne la scheda e lo storico dedicato:"
        )
        self.input_filter_matching.clear()

        self.table_matching_products.blockSignals(True)
        self.table_matching_products.setSortingEnabled(False)
        self.table_matching_products.clearSelection()
        self.table_matching_products.setRowCount(len(products))

        for i, prod in enumerate(products):
            item_code = SortableTableWidgetItem(prod.code)
            item_code.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 0, item_code)

            item_name = QTableWidgetItem(prod.name or "-")
            item_name.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 1, item_name)

            cat_str = f"{prod.type or ''} / {prod.category or 'Standard'}"
            item_cat = QTableWidgetItem(cat_str)
            item_cat.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 2, item_cat)

            cost_val = float(prod.production_cost or 0.0)
            cost_str = f"€ {cost_val:.2f}" if cost_val else "-"
            item_cost = SortableTableWidgetItem(cost_str, sort_value=cost_val)
            item_cost.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 3, item_cost)

            list_val = float(prod.list_price or 0.0)
            list_str = f"€ {list_val:.2f}" if list_val else "-"
            item_list = SortableTableWidgetItem(list_str, sort_value=list_val)
            item_list.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 4, item_list)

            bkode_info = []
            if prod.drawing_number:
                bkode_info.append(f"Dis: {prod.drawing_number}")
            if prod.bkode_id:
                bkode_info.append(f"BK: {prod.bkode_id}")
            item_bkode = QTableWidgetItem(" | ".join(bkode_info) if bkode_info else "-")
            item_bkode.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 5, item_bkode)

            leg_codes = [l.legacy_code for l in prod.legacy_codes if l.legacy_code]
            item_leg = QTableWidgetItem(", ".join(leg_codes) if leg_codes else "-")
            item_leg.setData(Qt.ItemDataRole.UserRole, prod.code)
            self.table_matching_products.setItem(i, 6, item_leg)

        self.table_matching_products.setSortingEnabled(True)
        self.table_matching_products.blockSignals(False)
        self.box_matching_products.setVisible(True)
        self.table_matching_products.setVisible(True)
        self.input_filter_matching.setVisible(True)
        self.btn_toggle_matching.setText("Comprimi ▲")

        # Assicura un'altezza iniziale generosa per la finestra dei risultati nel separatore
        sizes = self.main_splitter.sizes()
        if sizes and sizes[0] < 280:
            total_h = sum(sizes) if sum(sizes) > 0 else 800
            target_top = min(340, max(280, int(total_h * 0.4)))
            self.main_splitter.setSizes([target_top, max(300, total_h - target_top)])

    def _toggle_matching_products(self):
        is_vis = self.table_matching_products.isVisible()
        self.table_matching_products.setVisible(not is_vis)
        self.input_filter_matching.setVisible(not is_vis)
        self.btn_toggle_matching.setText("Espandi Lista ▼" if is_vis else "Comprimi ▲")
        if not is_vis:
            sizes = self.main_splitter.sizes()
            total_h = sum(sizes) if sum(sizes) > 0 else 800
            target_top = min(340, max(280, int(total_h * 0.4)))
            self.main_splitter.setSizes([target_top, max(300, total_h - target_top)])

    def _filter_matching_products_table(self):
        text = self.input_filter_matching.text().strip().lower()
        for row in range(self.table_matching_products.rowCount()):
            if not text:
                self.table_matching_products.setRowHidden(row, False)
                continue
            match = False
            for col in range(self.table_matching_products.columnCount()):
                item = self.table_matching_products.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table_matching_products.setRowHidden(row, not match)

    def _on_matching_product_selected(self):
        row = self.table_matching_products.currentRow()
        prod_code = None
        if row >= 0:
            item = self.table_matching_products.item(row, 0)
            if item:
                prod_code = item.data(Qt.ItemDataRole.UserRole)

        if not prod_code:
            selected = self.table_matching_products.selectedItems()
            if selected:
                prod_code = selected[0].data(Qt.ItemDataRole.UserRole)
                if not prod_code and selected[0].row() >= 0:
                    it0 = self.table_matching_products.item(selected[0].row(), 0)
                    if it0:
                        prod_code = it0.data(Qt.ItemDataRole.UserRole)

        if prod_code:
            self.load_product_detail(prod_code)

    def load_product_detail(self, product_code: str):
        prod_360 = self.controller.get_product_360(product_code)
        if not prod_360 or not prod_360.get('product'):
            self.box_360.setVisible(False)
            return

        prod = prod_360['product']
        self.display_product_360(prod_360)

        # Costruisce codici equivalenti ESCLUSIVAMENTE per questo articolo
        equivalent_codes = [prod.code]
        for leg in prod_360.get('legacy_codes', []):
            lc = (leg.legacy_code or '').strip()
            if lc and len(lc) >= 2:
                equivalent_codes.append(lc)
        for sp in prod_360.get('supplier_products', []):
            sc = (sp.supplier_code or '').strip()
            if sc and len(sc) >= 2:
                equivalent_codes.append(sc)

        supplier_filter = self.combo_supplier.currentData()
        current_step = {
            'words': [],
            'search_code': True,
            'search_desc': False,
            'supplier': supplier_filter,
            'equivalent_codes': equivalent_codes
        }

        try:
            p_results = self.controller.search_items([current_step])
            self.last_p_results = p_results
            self.display_purchases(p_results)

            s_results = self.controller.search_sales_items([current_step])
            self.last_s_results = s_results
            self.display_sales(s_results)

            price_data = self.controller.get_product_price_lists(prod.code)
            self.display_price_lists(price_data)

            self.status_label.setText(
                f"Scheda Articolo: {prod.code} - {prod.name} | "
                f"Risultati: {len(p_results)} righe acquisto | {len(s_results)} righe vendita | "
                f"{len(price_data.get('purchase_lists', []))} listini acquisto | {len(price_data.get('sales_lists', []))} listini vendita."
            )
        except Exception as e:
            self.status_label.setText(f"Errore caricamento storico articolo: {e}")

    def display_price_lists(self, price_data: dict):
        p_lists = price_data.get('purchase_lists', [])
        s_lists = price_data.get('sales_lists', [])

        # 1. Popola tabella Acquisti
        self.table_purchase_prices.setRowCount(len(p_lists))
        for row, it in enumerate(p_lists):
            self.table_purchase_prices.setItem(row, 0, QTableWidgetItem(it.get('list_code', '')))
            self.table_purchase_prices.setItem(row, 1, QTableWidgetItem(it.get('list_description', '')))
            self.table_purchase_prices.setItem(row, 2, QTableWidgetItem(it.get('partner_name', '')))
            self.table_purchase_prices.setItem(row, 3, QTableWidgetItem(it.get('unit_measure', 'NR')))
            
            bp = it.get('base_price', 0.0)
            self.table_purchase_prices.setItem(row, 4, SortableTableWidgetItem(f"€ {bp:.2f}" if bp else "-", sort_value=bp))
            
            sc1 = it.get('discount_1', 0.0)
            self.table_purchase_prices.setItem(row, 5, SortableTableWidgetItem(f"{sc1:.1f}%" if sc1 else "-", sort_value=sc1))
            
            sc2 = it.get('discount_2', 0.0)
            self.table_purchase_prices.setItem(row, 6, SortableTableWidgetItem(f"{sc2:.1f}%" if sc2 else "-", sort_value=sc2))
            
            net = it.get('net_price', bp)
            item_net = SortableTableWidgetItem(f"€ {net:.2f}" if net else "-", sort_value=net)
            self.table_purchase_prices.setItem(row, 7, item_net)
            
            validity = []
            if it.get('valid_from'):
                validity.append(f"Dal {it['valid_from']}")
            if it.get('valid_to'):
                validity.append(f"Al {it['valid_to']}")
            self.table_purchase_prices.setItem(row, 8, QTableWidgetItem(" ".join(validity) if validity else "Sempre valido"))

        # 2. Popola tabella Vendite
        self.table_sales_prices.setRowCount(len(s_lists))
        for row, it in enumerate(s_lists):
            self.table_sales_prices.setItem(row, 0, QTableWidgetItem(it.get('list_code', '')))
            self.table_sales_prices.setItem(row, 1, QTableWidgetItem(it.get('list_description', '')))
            self.table_sales_prices.setItem(row, 2, QTableWidgetItem(it.get('partner_name', 'Listino Generale')))
            self.table_sales_prices.setItem(row, 3, QTableWidgetItem(it.get('unit_measure', 'NR')))
            
            bp = it.get('base_price', 0.0)
            self.table_sales_prices.setItem(row, 4, SortableTableWidgetItem(f"€ {bp:.2f}" if bp else "-", sort_value=bp))
            
            sc1 = it.get('discount_1', 0.0)
            self.table_sales_prices.setItem(row, 5, SortableTableWidgetItem(f"{sc1:.1f}%" if sc1 else "-", sort_value=sc1))
            
            net = it.get('net_price', bp)
            item_net = SortableTableWidgetItem(f"€ {net:.2f}" if net else "-", sort_value=net)
            self.table_sales_prices.setItem(row, 6, item_net)
            
            validity = []
            if it.get('valid_from'):
                validity.append(f"Dal {it['valid_from']}")
            if it.get('valid_to'):
                validity.append(f"Al {it['valid_to']}")
            self.table_sales_prices.setItem(row, 7, QTableWidgetItem(" ".join(validity) if validity else "Sempre valido"))

        # 3. Aggiorna riga box_360
        info_parts = []
        if p_lists:
            top_p = p_lists[0]
            disc_str = f" (sc. {top_p['discount_1']:.0f}%)" if top_p.get('discount_1') else ""
            info_parts.append(f"Listino Acquisto: {top_p['partner_name']} € {top_p['net_price']:.2f}{disc_str}")
        if s_lists:
            top_s = s_lists[0]
            info_parts.append(f"Listino Vendita: € {top_s['net_price']:.2f} ({top_s['partner_name']})")

        if info_parts:
            self.lbl_art_price_lists.setText(" | ".join(info_parts))
        else:
            self.lbl_art_price_lists.setText("Listini B-Kode: Nessun listino associato a questo codice")


    def _perform_fallback_invoice_search(self, text, supplier_filter, search_code, search_desc):
        norm_text = re.sub(r'\b([a-zA-Z])\s+(\d+)\b', r'\1\2', text, flags=re.IGNORECASE)
        stopwords = {'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'da', 'in', 'con', 'su', 'per', 'del', 'della', 'dei', 'degli'}
        raw_words = [w for w in re.split(r'[\s%]+', norm_text) if w]
        words = [w for w in raw_words if w.lower() not in stopwords]
        if not words and raw_words:
            words = raw_words

        current_step = {
            'words': words,
            'search_code': search_code,
            'search_desc': search_desc,
            'supplier': supplier_filter,
            'equivalent_codes': []
        }

        if not self.cb_incremental.isChecked():
            self.active_search_steps = [current_step]
        else:
            self.active_search_steps.append(current_step)

        try:
            p_results = self.controller.search_items(self.active_search_steps)
            self.last_p_results = p_results
            self.display_purchases(p_results)

            s_results = self.controller.search_sales_items(self.active_search_steps)
            self.last_s_results = s_results
            self.display_sales(s_results)

            self.status_label.setText(
                f"Nessun articolo a catalogo. Storico fatture: {len(p_results)} righe acquisto | {len(s_results)} righe vendita trovate per '{text}'."
            )
        except Exception as e:
            self.status_label.setText(f"Errore durante la ricerca fatture: {e}")
            if self.cb_incremental.isChecked():
                self.active_search_steps.pop()

    def _on_grouping_changed(self):
        if hasattr(self, 'last_p_results'):
            self.display_purchases(self.last_p_results)
        if hasattr(self, 'last_s_results'):
            self.display_sales(self.last_s_results)

    def display_product_360(self, p_data):
        if not p_data or not p_data.get('product'):
            self.box_360.setVisible(False)
            return

        prod = p_data['product']
        legacy_codes = p_data.get('legacy_codes', [])
        supp_prods = p_data.get('supplier_products', [])

        self.current_product = prod
        self.lbl_art_master.setText(f"Codice Master: {prod.code}")
        self.lbl_art_desc.setText(f"Descrizione: {prod.name}")
        self.lbl_art_cat.setText(f"Tipo/Cat: {prod.type} / {prod.category or 'Standard'}")
        self.lbl_art_cost.setText(f"Costo STD: € {prod.production_cost:.2f}" if prod.production_cost else "Costo STD: -")
        self.lbl_art_list.setText(f"Listino Vendita: € {prod.list_price:.2f}" if prod.list_price else "Listino Vendita: -")

        # Codici legacy (esplosi)
        if legacy_codes:
            leg_str = ", ".join([l.legacy_code for l in legacy_codes])
            self.lbl_art_legacy.setText(f"Codici Esploso / Vecchi ({len(legacy_codes)}): {leg_str}")
        else:
            self.lbl_art_legacy.setText("Codici Esploso / Vecchi: Nessuno")

        # Codici fornitori
        if supp_prods:
            supp_str = ", ".join([f"{sp.supplier_name or 'Forn'}: {sp.supplier_code}" for sp in supp_prods[:3]])
            self.lbl_art_supp.setText(f"Fornitori Collegati ({len(supp_prods)}): {supp_str}")
        else:
            self.lbl_art_supp.setText("Fornitori Collegati: Nessuno")

        # Riga 4: B-Kode / Conversione / Disegno
        bkode_parts = []
        if prod.bkode_id:
            bkode_parts.append(f"ID B-Kode: {prod.bkode_id} ({prod.bkode_type or 'Std'})")
        if prod.conversion_factor and prod.conversion_factor != 1.0:
            bkode_parts.append(f"Fattore Conv: {prod.conversion_factor:.4f} {prod.unit_measure}/{prod.purchase_um or 'KG'}")
        if prod.drawing_number:
            bkode_parts.append(f"Disegno/Specifica: {prod.drawing_number}")
        if prod.raw_material_class:
            bkode_parts.append(f"Classe: {prod.raw_material_class}")
        
        self.lbl_art_bkode.setText(" | ".join(bkode_parts) if bkode_parts else "Dati B-Kode: Standard")

        # Pulisce vecchi bottoni esplosi
        while self.layout_diagrams_btns.count():
            item = self.layout_diagrams_btns.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Ricerca esplosi in cui compare il ricambio
        diagrams = self.controller.get_diagrams_for_product(prod.code)
        if diagrams:
            for d in diagrams[:4]: # Mostra i primi 4 riscontri diretti
                btn_text = f"📄 {d['machine_model']} ({d['code']}) • Pos. {d['position_num']}"
                btn_diag = QPushButton(btn_text)
                btn_diag.setFixedHeight(28)
                btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_diag.setToolTip(f"Apri disegno tecnico PDF: {d['file_path']} (Pagina {d['page_number']})")
                btn_diag.setStyleSheet("""
                    QPushButton {
                        background-color: #E8F5E9;
                        color: #1B5E20;
                        font-weight: bold;
                        border: 1px solid #A5D6A7;
                        border-radius: 4px;
                        padding: 3px 10px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #C8E6C9;
                        border-color: #2E7D32;
                    }
                """)
                fpath = d['file_path']
                btn_diag.clicked.connect(lambda _, fp=fpath: self.controller.open_diagram_pdf(fp))
                self.layout_diagrams_btns.addWidget(btn_diag)
            self.layout_diagrams_btns.addStretch()
        else:
            lbl_none = QLabel("Nessun disegno esploso associato.")
            lbl_none.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
            self.layout_diagrams_btns.addWidget(lbl_none)
            self.layout_diagrams_btns.addStretch()

        # Popola Distinta Base e Ciclo Lavorazioni nel Tab 3
        materials = p_data.get('materials', [])
        operations = p_data.get('operations', [])
        self.display_production_data(prod, materials, operations)

        self.box_360.setVisible(True)

    def _on_recalculate_cut(self):
        if not hasattr(self, 'current_product') or not self.current_product:
            return
        prod = self.current_product
        try:
            length_mm = float(self.input_cut_len.text().replace(',', '.'))
        except ValueError:
            self.lbl_calc_result.setText("Inserire una lunghezza valida in mm.")
            return

        res = self.controller.calculate_raw_material_cut(prod.code, length_mm)
        if "error" in res:
            self.lbl_calc_result.setText(res["error"])
        else:
            self.lbl_calc_result.setText(
                f"Spezzone {res['length_mm']:.0f} mm ({res['length_m']:.3f} m) ➔ "
                f"Peso: {res['weight_kg']:.3f} kg | Prezzo: € {res['price_per_kg']:.2f}/{res['purchase_um']} ➔ "
                f"COSTO TOTALE: € {res['total_cost']:.2f} ({res['price_source']})"
            )

    def display_production_data(self, prod, materials, operations):
        # 1. Calcolatore taglio materiale (attivo se conversion_factor presente e != 1 o se UM acquisto diversa da UM magazzino)
        has_conv = (prod.conversion_factor and prod.conversion_factor > 0 and prod.conversion_factor != 1.0) or (prod.purchase_um and prod.purchase_um != prod.unit_measure)
        if has_conv:
            self.box_calc_material.setVisible(True)
            self._on_recalculate_cut()
        else:
            self.box_calc_material.setVisible(False)

        # 2. Popola Distinta Materiali
        self.table_bom.setSortingEnabled(False)
        self.table_bom.setRowCount(len(materials))
        tot_mat_cost = 0.0

        for i, m in enumerate(materials):
            subtot = float(m.quantity or 1.0) * float(m.unit_cost or 0.0)
            tot_mat_cost += subtot
            self.table_bom.setItem(i, 0, SortableTableWidgetItem(str(m.line_num), sort_value=m.line_num))
            self.table_bom.setItem(i, 1, QTableWidgetItem(m.component_code))
            self.table_bom.setItem(i, 2, QTableWidgetItem(m.description or "-"))
            self.table_bom.setItem(i, 3, QTableWidgetItem(m.unit_measure or "NR"))
            self.table_bom.setItem(i, 4, SortableTableWidgetItem(f"{m.quantity:.3f}", sort_value=m.quantity))
            self.table_bom.setItem(i, 5, SortableTableWidgetItem(f"€ {m.unit_cost:.2f}", sort_value=m.unit_cost))
            self.table_bom.setItem(i, 6, SortableTableWidgetItem(f"€ {subtot:.2f}", sort_value=subtot))

        self.table_bom.setSortingEnabled(True)

        # 3. Popola Ciclo Lavorazioni
        self.table_routing.setSortingEnabled(False)
        self.table_routing.setRowCount(len(operations))
        tot_run_h = 0.0
        tot_setup_h = 0.0
        tot_ops_cost = 0.0

        for i, op in enumerate(operations):
            run_h = float(op.operation_hours or 0.0)
            setup_h = float(op.setup_hours or 0.0)
            rate = float(op.hourly_rate or 0.0)
            line_cost = (run_h + setup_h) * rate
            tot_run_h += run_h
            tot_setup_h += setup_h
            tot_ops_cost += line_cost

            self.table_routing.setItem(i, 0, SortableTableWidgetItem(str(op.sequence), sort_value=op.sequence))
            self.table_routing.setItem(i, 1, QTableWidgetItem(op.phase_code))
            self.table_routing.setItem(i, 2, QTableWidgetItem(op.description or "-"))
            self.table_routing.setItem(i, 3, SortableTableWidgetItem(f"{setup_h:.1f} h", sort_value=setup_h))
            self.table_routing.setItem(i, 4, SortableTableWidgetItem(f"{run_h:.1f} h", sort_value=run_h))
            self.table_routing.setItem(i, 5, SortableTableWidgetItem(f"€ {rate:.2f}/h", sort_value=rate))
            self.table_routing.setItem(i, 6, SortableTableWidgetItem(f"€ {line_cost:.2f}", sort_value=line_cost))

        self.table_routing.setSortingEnabled(True)

        # 4. Aggiorna riepilogo costi
        tot_prod_cost = tot_mat_cost + tot_ops_cost
        if materials or operations:
            self.lbl_prod_cost_summary.setText(
                f"🔩 Costo Materiali: € {tot_mat_cost:,.2f}  |  "
                f"⏱️ Ore Macchina: {tot_run_h:.1f} h (Attrezzo: {tot_setup_h:.1f} h)  |  "
                f"⚙️ Costo Fasi: € {tot_ops_cost:,.2f}  |  "
                f"💰 COSTO PRODUZIONE TOTALE: € {tot_prod_cost:,.2f}"
            )
            self.tabs.setTabText(2, f"Distinta & Lavorazioni ({len(materials)} mat, {len(operations)} fasi)")
        elif has_conv:
            self.lbl_prod_cost_summary.setText(
                f"📦 Articolo Commerciale con Fattore di Conversione: {prod.conversion_factor:.4f} {prod.unit_measure}/{prod.purchase_um or 'KG'}"
            )
            self.tabs.setTabText(2, "Calcolatore Taglio Materiale")
        else:
            self.lbl_prod_cost_summary.setText("Nessuna distinta o ciclo di lavorazione associato a questo articolo.")
            self.tabs.setTabText(2, "Distinta Base & Lavorazioni (Produzione)")

    def display_purchases(self, results):
        self.table_purchases.setSortingEnabled(False)
        
        # Raggruppamento per fattura (1 sola riga per documento)
        if self.cb_group_invoices.isChecked():
            from collections import OrderedDict
            grouped = OrderedDict()
            for riga in results:
                inv_id = riga.invoice_id
                if inv_id not in grouped:
                    grouped[inv_id] = []
                grouped[inv_id].append(riga)

            self.table_purchases.setRowCount(len(grouped))
            for i, (inv_id, items) in enumerate(grouped.items()):
                inv = items[0].invoice
                date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
                item_num = SortableTableWidgetItem(str(inv.number), sort_value=inv.number)
                item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
                self.table_purchases.setItem(i, 0, item_num)
                self.table_purchases.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=inv.date))
                self.table_purchases.setItem(i, 2, QTableWidgetItem(inv.supplier.name if inv.supplier else "-"))
                self.table_purchases.setItem(i, 3, QTableWidgetItem(f"({len(items)} articoli)"))
                self.table_purchases.setItem(i, 4, QTableWidgetItem("-"))
                
                first_desc = items[0].description
                desc_str = f"{first_desc} (+ altri {len(items)-1})" if len(items) > 1 else first_desc
                self.table_purchases.setItem(i, 5, QTableWidgetItem(desc_str))
                
                tot_qty = sum(it.quantity or 0.0 for it in items)
                self.table_purchases.setItem(i, 6, SortableTableWidgetItem(f"{tot_qty:.2f}", sort_value=tot_qty))
                
                tot_amt = float(inv.total_amount or 0.0)
                self.table_purchases.setItem(i, 7, SortableTableWidgetItem(f"€ {tot_amt:,.2f}", sort_value=tot_amt))
                self.table_purchases.setItem(i, 8, SortableTableWidgetItem(f"€ {tot_amt:,.2f}", sort_value=tot_amt))
        else:
            self.table_purchases.setRowCount(len(results))
            for i, riga in enumerate(results):
                item_num = SortableTableWidgetItem(str(riga.invoice.number), sort_value=riga.invoice.number)
                item_num.setData(Qt.ItemDataRole.UserRole, riga.invoice.id)
                self.table_purchases.setItem(i, 0, item_num)
                
                date_str = riga.invoice.date.strftime("%d/%m/%Y") if riga.invoice.date else "-"
                self.table_purchases.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=riga.invoice.date))
                self.table_purchases.setItem(i, 2, QTableWidgetItem(riga.invoice.supplier.name if riga.invoice.supplier else "-"))
                self.table_purchases.setItem(i, 3, QTableWidgetItem(riga.code or "-"))
                self.table_purchases.setItem(i, 4, QTableWidgetItem(riga.customer_code or "-"))
                self.table_purchases.setItem(i, 5, QTableWidgetItem(riga.description))
                self.table_purchases.setItem(i, 6, SortableTableWidgetItem(f"{riga.quantity:.2f}", sort_value=riga.quantity))
                self.table_purchases.setItem(i, 7, SortableTableWidgetItem(f"€ {riga.unit_price:.2f}", sort_value=riga.unit_price))
                self.table_purchases.setItem(i, 8, SortableTableWidgetItem(f"€ {riga.total_price:.2f}", sort_value=riga.total_price))
            
        self.table_purchases.setSortingEnabled(True)

    def display_sales(self, results):
        self.table_sales.setSortingEnabled(False)
        
        # Raggruppamento per fattura (1 sola riga per documento)
        if self.cb_group_invoices.isChecked():
            from collections import OrderedDict
            grouped = OrderedDict()
            for item in results:
                inv_id = item.invoice_id
                if inv_id not in grouped:
                    grouped[inv_id] = []
                grouped[inv_id].append(item)

            self.table_sales.setRowCount(len(grouped))
            for i, (inv_id, items) in enumerate(grouped.items()):
                inv = items[0].invoice
                date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
                
                item_num = SortableTableWidgetItem(f"{inv.number}/{inv.year}", sort_value=inv.number)
                item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
                self.table_sales.setItem(i, 0, item_num)
                self.table_sales.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=inv.date))
                self.table_sales.setItem(i, 2, QTableWidgetItem(inv.customer.name if inv.customer else "-"))
                self.table_sales.setItem(i, 3, QTableWidgetItem(f"({len(items)} articoli)"))
                
                first_desc = items[0].description
                desc_str = f"{first_desc} (+ altri {len(items)-1})" if len(items) > 1 else first_desc
                self.table_sales.setItem(i, 4, QTableWidgetItem(desc_str))
                self.table_sales.setItem(i, 5, QTableWidgetItem("DOC"))
                
                tot_qty = sum(it.quantity or 0.0 for it in items)
                qty_str = f"{int(tot_qty)}" if tot_qty == int(tot_qty) else f"{tot_qty:.2f}"
                self.table_sales.setItem(i, 6, SortableTableWidgetItem(qty_str, sort_value=tot_qty))
                
                tot_amt = float(inv.total_amount or 0.0)
                self.table_sales.setItem(i, 7, SortableTableWidgetItem(f"€ {tot_amt:,.2f}", sort_value=tot_amt))
                self.table_sales.setItem(i, 8, SortableTableWidgetItem("-", sort_value=0))
        else:
            self.table_sales.setRowCount(len(results))
            for i, item in enumerate(results):
                inv = item.invoice
                date_str = inv.date.strftime("%d/%m/%Y") if inv.date else "-"
                
                item_num = SortableTableWidgetItem(f"{inv.number}/{inv.year}", sort_value=inv.number)
                item_num.setData(Qt.ItemDataRole.UserRole, inv.id)
                self.table_sales.setItem(i, 0, item_num)
                self.table_sales.setItem(i, 1, SortableTableWidgetItem(date_str, sort_value=inv.date))
                self.table_sales.setItem(i, 2, QTableWidgetItem(inv.customer.name if inv.customer else "-"))
                self.table_sales.setItem(i, 3, QTableWidgetItem(item.raw_code or "-"))
                self.table_sales.setItem(i, 4, QTableWidgetItem(item.description))
                self.table_sales.setItem(i, 5, QTableWidgetItem(item.unit_measure or "NR"))
                q_val = item.quantity or 0.0
                q_str = f"{int(q_val)}" if q_val == int(q_val) else f"{q_val:.2f}"
                self.table_sales.setItem(i, 6, SortableTableWidgetItem(q_str, sort_value=q_val))
                self.table_sales.setItem(i, 7, SortableTableWidgetItem(f"€ {item.unit_price:.2f}", sort_value=item.unit_price))
                self.table_sales.setItem(i, 8, SortableTableWidgetItem(f"{item.discount:.1f}%" if item.discount else "-", sort_value=item.discount))
            
        self.table_sales.setSortingEnabled(True)

    def handle_double_click_purchase(self, row, col):
        invoice_id = self.table_purchases.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if invoice_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=invoice_id, invoice_type="purchase")

    def handle_double_click_sales(self, row, col):
        invoice_id = self.table_sales.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if invoice_id and hasattr(self.main_window, 'show_invoice_detail'):
            self.main_window.show_invoice_detail(invoice_id=invoice_id, invoice_type="sale")

    def refresh_data(self):
        # Aggiorna solo i filtri del combo fornitore, senza toccare i risultati di ricerca già visualizzati
        self._populate_filters()
