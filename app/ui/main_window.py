from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QToolBar, 
                             QStatusBar, QStackedWidget)
from PyQt6.QtGui import QAction, QIcon
from .dashboard import DashboardWidget
from .import_dialog import ImportDialog
from .analysis import AnalysisWidget 
from .reports import ReportWidget
from .article_search import ArticleSearchWidget

class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        
        self.setWindowTitle("Analisi Costi Fatture")
        self.resize(1200, 800)
        
        self.init_ui()
        
    def init_ui(self):
        # Toolbar
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        act_dashboard = QAction("Dashboard", self)
        act_dashboard.triggered.connect(lambda: self.switch_view(0))
        toolbar.addAction(act_dashboard)
        
        act_analysis = QAction("Analisi Prezzi", self)
        act_analysis.triggered.connect(lambda: self.switch_view(1))
        toolbar.addAction(act_analysis)
        
        # New Action for Article Search
        act_search = QAction("Ricerca Articoli", self)
        act_search.triggered.connect(lambda: self.switch_view(3))
        toolbar.addAction(act_search)
        
        act_reports = QAction("Report", self)
        act_reports.triggered.connect(lambda: self.switch_view(2))
        toolbar.addAction(act_reports)
        
        toolbar.addSeparator()

        act_import = QAction("Importa", self)
        act_import.triggered.connect(self.show_import_dialog)
        toolbar.addAction(act_import)
        
        act_refresh = QAction("Aggiorna Dati", self)
        act_refresh.triggered.connect(self.refresh_current_view)
        toolbar.addAction(act_refresh)
        
        toolbar.addSeparator()
        
        act_change_db = QAction("Cambia Database", self)
        act_change_db.triggered.connect(self.change_database)
        toolbar.addAction(act_change_db)

        # Central Widget (Stacked)
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)
        
        # Views
        self.dashboard = DashboardWidget(self.controller)
        self.central_stack.addWidget(self.dashboard)
        
        self.analysis = AnalysisWidget(self.controller)
        self.central_stack.addWidget(self.analysis)
        
        self.reports = ReportWidget(self.controller)
        self.central_stack.addWidget(self.reports)

        # View 3: Article Search
        self.article_search = ArticleSearchWidget(self.controller, self)
        self.central_stack.addWidget(self.article_search)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
    def switch_view(self, index):
        self.central_stack.setCurrentIndex(index)
        self.refresh_current_view()

    def show_import_dialog(self):
        dlg = ImportDialog(self.controller, self)
        if dlg.exec():
            self.refresh_current_view()
            
    def refresh_current_view(self):
        current = self.central_stack.currentWidget()
        if hasattr(current, 'refresh_data'):
            current.refresh_data()
        self.status_bar.showMessage("Dati aggiornati.")

    def show_invoice_detail_by_id(self, invoice_id: int):
        """Apre il dialogo dettaglio fattura dalla ricerca articoli."""
        from .invoice_detail import InvoiceDetailDialog
        dlg = InvoiceDetailDialog(invoice_id, parent=self)
        dlg.exec()
        
    def change_database(self):
        from PyQt6.QtWidgets import QMessageBox
        from app.utils.settings import SettingsManager
        import sys
        import os
        
        reply = QMessageBox.question(
            self, "Cambia Database", 
            "L'applicazione verrà riavviata per permetterti di selezionare un nuovo file database. Continuare?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            settings = SettingsManager()
            settings.set_remember_db(False) 
            # Riavvia il processo corrente
            os.execl(sys.executable, sys.executable, *sys.argv)
