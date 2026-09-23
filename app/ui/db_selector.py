from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QCheckBox,
                             QTabWidget, QWidget, QFormLayout, QMessageBox)
from PyQt6.QtCore import Qt
import os

DEFAULT_SYNOLOGY_PG = "postgresql+psycopg2://angeleri:AngeleriPassword2026!@192.168.1.38:5433/angeleri_db"

class DatabaseSelector(QDialog):
    def __init__(self, current_path=None, remember=False):
        super().__init__()
        self.setWindowTitle("Configurazione Connessione Database")
        self.setMinimumWidth(550)
        
        self.current_path = current_path or DEFAULT_SYNOLOGY_PG
        self.remember = remember
        
        layout = QVBoxLayout(self)
        
        # Tabs: Server Synology vs File Locale SQLite
        self.tabs = QTabWidget()
        
        # TAB 1: Server Synology (PostgreSQL)
        self.tab_server = QWidget()
        tab_server_layout = QFormLayout(self.tab_server)
        
        self.edit_host = QLineEdit("192.168.1.38")
        self.edit_port = QLineEdit("5433")
        self.edit_db = QLineEdit("angeleri_db")
        self.edit_user = QLineEdit("angeleri")
        self.edit_pass = QLineEdit("AngeleriPassword2026!")
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Password)
        
        tab_server_layout.addRow("Indirizzo IP Synology:", self.edit_host)
        tab_server_layout.addRow("Porta Server:", self.edit_port)
        tab_server_layout.addRow("Nome Database:", self.edit_db)
        tab_server_layout.addRow("Utente:", self.edit_user)
        tab_server_layout.addRow("Password:", self.edit_pass)
        
        btn_test = QPushButton("Test Connessione Synology")
        btn_test.clicked.connect(self.test_synology_connection)
        tab_server_layout.addRow("", btn_test)
        
        self.tabs.addTab(self.tab_server, "Server Synology (Consigliato)")
        
        # TAB 2: File Locale SQLite (Fallback)
        self.tab_sqlite = QWidget()
        tab_sqlite_layout = QVBoxLayout(self.tab_sqlite)
        tab_sqlite_layout.addWidget(QLabel("Seleziona il file del database SQLite locale (.db):"))
        
        file_layout = QHBoxLayout()
        self.path_edit = QLineEdit(os.path.join(os.getcwd(), "invoices.db"))
        file_layout.addWidget(self.path_edit)
        
        btn_browse = QPushButton("Sfoglia...")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(btn_browse)
        tab_sqlite_layout.addLayout(file_layout)
        tab_sqlite_layout.addStretch()
        
        self.tabs.addTab(self.tab_sqlite, "File Locale SQLite (Offline)")
        
        # Seleziona il tab attivo in base a current_path
        if self.current_path.startswith("sqlite://") or self.current_path.endswith(".db"):
            self.tabs.setCurrentIndex(1)
            self.path_edit.setText(self.current_path.replace("sqlite:///", ""))
        else:
            self.tabs.setCurrentIndex(0)
            
        layout.addWidget(self.tabs)
        
        self.check_remember = QCheckBox("Memorizza questa scelta per i prossimi avvii")
        self.check_remember.setChecked(self.remember)
        layout.addWidget(self.check_remember)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Conferma e Connetti")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("Esci")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)

    def test_synology_connection(self):
        try:
            import psycopg2
            host = self.edit_host.text().strip()
            port = int(self.edit_port.text().strip())
            dbname = self.edit_db.text().strip()
            user = self.edit_user.text().strip()
            password = self.edit_pass.text().strip()
            
            conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3)
            conn.close()
            QMessageBox.information(self, "Connessione Riuscita", "Connessione a PostgreSQL su Synology avvenuta con successo!")
        except Exception as e:
            QMessageBox.critical(self, "Errore Connessione", f"Impossibile connettersi al Synology:\n{e}")

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona Database SQLite", os.getcwd(), "Database Files (*.db);;All Files (*)"
        )
        if file_path:
            self.path_edit.setText(file_path)

    def get_result(self):
        if self.tabs.currentIndex() == 0:
            # Synology PostgreSQL URL
            host = self.edit_host.text().strip()
            port = self.edit_port.text().strip()
            dbname = self.edit_db.text().strip()
            user = self.edit_user.text().strip()
            password = self.edit_pass.text().strip()
            url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
            return url, self.check_remember.isChecked()
        else:
            # SQLite Path
            return self.path_edit.text().strip(), self.check_remember.isChecked()
