from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QStatusBar, QStackedWidget, QLabel, QFrame, 
                             QButtonGroup, QMessageBox)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon

from .dashboard import DashboardWidget
from .import_dialog import ImportDialog
from .analysis import AnalysisWidget 
from .reports import ReportWidget
from .article_search import ArticleSearchWidget
from .customers_view import CustomersWidget
from .suppliers_view import SuppliersWidget
from .products_view import ProductsWidget
from .work_orders_view import WorkOrdersWidget
from .ai_assistant_view import AIAssistantWidget
from .exploded_diagrams_view import ExplodedDiagramsWidget

class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        
        self.setWindowTitle("Gestionale Angeleri - Officina Meccanica")
        self.resize(1380, 860)
        self._open_invoice_windows = {}
        
        self.init_ui()
        
        # Inizializza Background Sync B-Kode distribuito
        from app.utils.background_sync import BackgroundSyncManager
        from app.utils.settings import SettingsManager
        interval = SettingsManager().get_bkode_sync_interval()
        self.sync_manager = BackgroundSyncManager(interval_minutes=interval, parent=self)
        self.sync_manager.status_updated.connect(self._on_bkode_sync_updated)
        self.sync_manager.start()
        
    def init_ui(self):
        main_container = QWidget()
        main_layout = QHBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(main_container)

        # ====================================================
        # SIDEBAR LATERALE (STILE GESTIONALE MODERNO)
        # ====================================================
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #1E293B;
                color: #F8FAFC;
            }
            QPushButton {
                background-color: transparent;
                color: #CBD5E1;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                padding-left: 18px;
                height: 42px;
                border: none;
                border-radius: 6px;
                margin: 2px 8px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: #0284C7;
                color: #FFFFFF;
                font-weight: bold;
            }
        """)
        
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 15, 0, 15)
        sidebar_layout.setSpacing(4)

        # Header Logo / Azienda
        header_box = QVBoxLayout()
        header_box.setContentsMargins(20, 10, 20, 20)
        lbl_brand = QLabel("OFFICINA ANGELERI")
        lbl_brand.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        lbl_brand.setStyleSheet("color: #38BDF8; letter-spacing: 1px;")
        
        lbl_sub = QLabel("Gestionale & Ricambi")
        lbl_sub.setFont(QFont("Arial", 10))
        lbl_sub.setStyleSheet("color: #94A3B8;")
        
        header_box.addWidget(lbl_brand)
        header_box.addWidget(lbl_sub)
        sidebar_layout.addLayout(header_box)

        # Separatore
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #334155; margin-bottom: 10px;")
        sidebar_layout.addWidget(sep1)

        # Gruppo Bottoni Navigazione
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_nav_dash = QPushButton("📊  Dashboard")
        self.btn_nav_dash.setCheckable(True)
        self.btn_nav_dash.setChecked(True)
        self.btn_nav_dash.clicked.connect(lambda: self.switch_view(0))
        self.nav_group.addButton(self.btn_nav_dash)
        sidebar_layout.addWidget(self.btn_nav_dash)

        self.btn_nav_cust = QPushButton("👥  Clienti")
        self.btn_nav_cust.setCheckable(True)
        self.btn_nav_cust.clicked.connect(lambda: self.switch_view(1))
        self.nav_group.addButton(self.btn_nav_cust)
        sidebar_layout.addWidget(self.btn_nav_cust)

        self.btn_nav_supp = QPushButton("🏭  Fornitori")
        self.btn_nav_supp.setCheckable(True)
        self.btn_nav_supp.clicked.connect(lambda: self.switch_view(2))
        self.nav_group.addButton(self.btn_nav_supp)
        sidebar_layout.addWidget(self.btn_nav_supp)

        self.btn_nav_prod = QPushButton("⚙️  Catalogo Ricambi")
        self.btn_nav_prod.setCheckable(True)
        self.btn_nav_prod.clicked.connect(lambda: self.switch_view(3))
        self.nav_group.addButton(self.btn_nav_prod)
        sidebar_layout.addWidget(self.btn_nav_prod)

        self.btn_nav_work = QPushButton("🛠️  Commesse Officina")
        self.btn_nav_work.setCheckable(True)
        self.btn_nav_work.clicked.connect(lambda: self.switch_view(4))
        self.nav_group.addButton(self.btn_nav_work)
        sidebar_layout.addWidget(self.btn_nav_work)

        self.btn_nav_search = QPushButton("🔍  Ricerca Ricambi 360°")
        self.btn_nav_search.setCheckable(True)
        self.btn_nav_search.clicked.connect(lambda: self.switch_view(5))
        self.nav_group.addButton(self.btn_nav_search)
        sidebar_layout.addWidget(self.btn_nav_search)

        self.btn_nav_rep = QPushButton("📈  Analisi & Report")
        self.btn_nav_rep.setCheckable(True)
        self.btn_nav_rep.clicked.connect(lambda: self.switch_view(6))
        self.nav_group.addButton(self.btn_nav_rep)
        sidebar_layout.addWidget(self.btn_nav_rep)

        self.btn_nav_diagrams = QPushButton("📖  Esplosi Macchine")
        self.btn_nav_diagrams.setCheckable(True)
        self.btn_nav_diagrams.clicked.connect(lambda: self.switch_view(7))
        self.nav_group.addButton(self.btn_nav_diagrams)
        sidebar_layout.addWidget(self.btn_nav_diagrams)

        self.btn_nav_ai = QPushButton("🤖  Assistente AI")
        self.btn_nav_ai.setCheckable(True)
        self.btn_nav_ai.clicked.connect(lambda: self.switch_view(8))
        self.nav_group.addButton(self.btn_nav_ai)
        sidebar_layout.addWidget(self.btn_nav_ai)

        sidebar_layout.addStretch()

        # Separatore inferiore
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #334155; margin: 10px 0;")
        sidebar_layout.addWidget(sep2)

        # Pulsanti Utility in basso
        btn_import = QPushButton("📥  Importa Fatture XML")
        btn_import.setStyleSheet("font-size: 12px; color: #94A3B8;")
        btn_import.clicked.connect(self.show_import_dialog)
        sidebar_layout.addWidget(btn_import)

        btn_refresh = QPushButton("🔄  Aggiorna Dati")
        btn_refresh.setStyleSheet("font-size: 12px; color: #94A3B8;")
        btn_refresh.clicked.connect(self.refresh_current_view)
        sidebar_layout.addWidget(btn_refresh)

        btn_bkode = QPushButton("🔄  B-Kode Cloud")
        btn_bkode.setStyleSheet("font-size: 12px; color: #94A3B8;")
        btn_bkode.clicked.connect(self.show_bkode_dialog)
        sidebar_layout.addWidget(btn_bkode)

        btn_db = QPushButton("💾  Database (Synology)")
        btn_db.setStyleSheet("font-size: 12px; color: #94A3B8;")
        btn_db.clicked.connect(self.change_database)
        sidebar_layout.addWidget(btn_db)

        main_layout.addWidget(sidebar)

        # ====================================================
        # AREA CENTRALE: QStackedWidget (Pagine Applicazione)
        # ====================================================
        self.central_stack = QStackedWidget()
        self.central_stack.setStyleSheet("background-color: #FFFFFF;")
        main_layout.addWidget(self.central_stack)

        # 0: Dashboard
        self.dashboard = DashboardWidget(self.controller)
        self.central_stack.addWidget(self.dashboard)

        # 1: Clienti
        self.customers_view = CustomersWidget(self.controller, self)
        self.central_stack.addWidget(self.customers_view)

        # 2: Fornitori
        self.suppliers_view = SuppliersWidget(self.controller, self)
        self.central_stack.addWidget(self.suppliers_view)

        # 3: Catalogo Ricambi
        self.products_view = ProductsWidget(self.controller, self)
        self.central_stack.addWidget(self.products_view)

        # 4: Commesse Officina
        self.work_orders_view = WorkOrdersWidget(self.controller, self)
        self.central_stack.addWidget(self.work_orders_view)

        # 5: Ricerca Ricambi 360° & Vocale
        self.article_search = ArticleSearchWidget(self.controller, self)
        self.central_stack.addWidget(self.article_search)

        # 6: Report & Analisi Prezzi
        self.reports = ReportWidget(self.controller)
        self.central_stack.addWidget(self.reports)

        # 7: Esplosi Macchine & Distinte PDF
        self.exploded_diagrams_view = ExplodedDiagramsWidget(self.controller, self)
        self.central_stack.addWidget(self.exploded_diagrams_view)

        # 8: Assistente AI Gemini
        self.ai_assistant_view = AIAssistantWidget(self.controller, self)
        self.central_stack.addWidget(self.ai_assistant_view)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Connesso al server Synology DS920+ (angeleri_db)")

        from app.utils.settings import SettingsManager
        has_creds = bool(SettingsManager().get_bkode_password() or SettingsManager().get_bkode_cookie())
        if has_creds:
            self.btn_bkode_status = QPushButton("🟢 B-Kode: In ascolto")
            self.btn_bkode_status.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 11px;")
            self.btn_bkode_status.setToolTip("Stato sincronizzazione automatica B-Kode. Clicca per configurare o forzare la sincronizzazione.")
        else:
            self.btn_bkode_status = QPushButton("🔴 B-Kode: Password mancante")
            self.btn_bkode_status.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 11px;")
            self.btn_bkode_status.setToolTip("Password B-Kode non inserita. Clicca qui per inserire la password e scaricare fatture e listini.")

        self.btn_bkode_status.setFlat(True)
        self.btn_bkode_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bkode_status.clicked.connect(self.show_bkode_dialog)
        self.status_bar.addPermanentWidget(self.btn_bkode_status)

    def switch_view(self, index):
        self.central_stack.setCurrentIndex(index)
        self.refresh_current_view()

    def show_import_dialog(self):
        dlg = ImportDialog(self.controller, self)
        if dlg.exec():
            self.refresh_current_view()

    def show_bkode_dialog(self):
        from app.ui.bkode_config_dialog import BKodeConfigDialog
        dlg = BKodeConfigDialog(self)
        dlg.sync_requested.connect(self.refresh_current_view)
        dlg.exec()

    def _on_bkode_sync_updated(self, msg: str):
        self.status_bar.showMessage(msg, 10000)
        if hasattr(self, 'btn_bkode_status'):
            if "mancant" in msg.lower() or "fallit" in msg.lower() or "errore" in msg.lower() or "non valid" in msg.lower():
                self.btn_bkode_status.setText("🔴 B-Kode: Password mancante")
                self.btn_bkode_status.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 11px;")
            elif "completata" in msg.lower() or "recente" in msg.lower():
                self.btn_bkode_status.setText("🟢 B-Kode: Sincronizzato")
                self.btn_bkode_status.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 11px;")
            elif "altra postazione" in msg.lower():
                self.btn_bkode_status.setText("🟡 B-Kode: Sync su altro PC")
                self.btn_bkode_status.setStyleSheet("color: #F57C00; font-weight: bold; font-size: 11px;")
            else:
                self.btn_bkode_status.setText("🟢 B-Kode: Attivo")
                self.btn_bkode_status.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 11px;")
            self.btn_bkode_status.setToolTip(msg)

    def refresh_current_view(self):
        current = self.central_stack.currentWidget()
        if hasattr(current, 'refresh_data'):
            current.refresh_data()
        self.status_bar.showMessage("Dati aggiornati dal server Synology.")

    def show_invoice_detail(self, invoice_id: int = None, invoice_type: str = "auto", invoice_number: str = None, invoice_year: int = None):
        """
        Apre una finestra di dettaglio fattura autonoma e NON MODALE.
        Consente di visualizzare la fattura senza bloccare la schermata principale,
        lasciando intatti e sempre visibili i risultati di ricerca o la conversazione dell'assistente AI.
        Permette anche di aprire e confrontare più fatture contemporaneamente a schermo.
        """
        from .invoice_detail import InvoiceDetailDialog
        if not hasattr(self, '_open_invoice_windows'):
            self._open_invoice_windows = {}

        key = f"{invoice_type}_{invoice_number}_{invoice_year}_{invoice_id}"
        
        # Se già aperta, portala semplicemente in primo piano
        if key in self._open_invoice_windows and self._open_invoice_windows[key] is not None:
            existing_dlg = self._open_invoice_windows[key]
            try:
                existing_dlg.show()
                existing_dlg.raise_()
                existing_dlg.activateWindow()
                return existing_dlg
            except RuntimeError:
                del self._open_invoice_windows[key]

        # IMPORTANTE: parent=None per evitare che Qt minimizzi/nasconda la MainWindow
        # quando questa finestra viene chiusa. La teniamo in vita manualmente nel dizionario.
        dlg = InvoiceDetailDialog(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            invoice_number=invoice_number,
            invoice_year=invoice_year,
            parent=None
        )
        
        # Posiziona leggermente sfalsata rispetto alla MainWindow per non coprirla completamente
        try:
            geo = self.geometry()
            offset = 35 * (len(self._open_invoice_windows) % 4)
            dlg.move(geo.x() + 90 + offset, geo.y() + 60 + offset)
        except Exception:
            pass

        def on_closed():
            self._open_invoice_windows.pop(key, None)
            # Riporta la MainWindow in primo piano senza interferire con la logica interna
            try:
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        dlg.destroyed.connect(on_closed)

        self._open_invoice_windows[key] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def show_invoice_detail_by_id(self, invoice_id: int = None, invoice_type: str = "auto", invoice_number: str = None, invoice_year: int = None):
        return self.show_invoice_detail(invoice_id=invoice_id, invoice_type=invoice_type, invoice_number=invoice_number, invoice_year=invoice_year)

    def change_database(self):
        import sys
        import os
        from app.utils.settings import SettingsManager
        
        reply = QMessageBox.question(
            self, "Configurazione Database", 
            "Vuoi aprire la schermata per cambiare o verificare la connessione al database Synology?\nL'applicazione si riavvierà.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            settings = SettingsManager()
            settings.set_remember_db(False) 
            os.execl(sys.executable, sys.executable, *sys.argv)
