import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLabel, QLineEdit, QPushButton, QSpinBox, 
    QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from app.utils.settings import SettingsManager
from app.utils.bkode_client import BKodeClient
from app.utils.background_sync import BKodeSyncEngine

logger = logging.getLogger(__name__)

class TestConnectionThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, username, password, cookie, parent=None):
        super().__init__(parent)
        self.username = username
        self.password = password
        self.cookie = cookie

    def run(self):
        try:
            client = BKodeClient(username=self.username, password=self.password, cookie=self.cookie)
            if self.password:
                ok = client.login(self.username, self.password)
                if ok:
                    self.finished.emit(True, "Accesso a B-Kode effettuato con successo!\nSessione autenticata.")
                else:
                    self.finished.emit(False, "Credenziali non valide o rifiutate dal server B-Kode.")
            elif self.cookie:
                client._apply_cookie(self.cookie)
                if client.ensure_authenticated():
                    self.finished.emit(True, "Cookie di sessione valido e verificato con successo!")
                else:
                    self.finished.emit(False, "Cookie di sessione scaduto o non valido.")
            else:
                self.finished.emit(False, "Inserisci una password o un cookie di sessione.")
        except Exception as e:
            self.finished.emit(False, f"Errore di rete durante la connessione: {e}")


class ForceSyncThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            engine = BKodeSyncEngine()
            res = engine.sync_all(force=True)
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"executed": False, "reason": str(e), "errors": [str(e)]})


class BKodeConfigDialog(QDialog):
    """Finestra di configurazione credenziali e sincronizzazione B-Kode."""
    
    sync_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Integrazione B-Kode Cloud")
        self.resize(520, 420)
        self.settings = SettingsManager()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Header con icona e spiegazione
        lbl_header = QLabel("🔄 Sincronizzazione B-Kode Cloud (Listini, Articoli, Fatture)")
        lbl_header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        lbl_header.setStyleSheet("color: #1565C0; margin-bottom: 5px;")
        layout.addWidget(lbl_header)

        lbl_desc = QLabel(
            "Configura le credenziali di accesso al portale B-Kode Cloud.\n"
            "Il sistema verificherà periodicamente nuovi listini fornitori/clienti, "
            "nuove fatture e nuovi articoli a catalogo.\n"
            "La sincronizzazione tra postazioni in officina è coordinata automaticamente "
            "tramite lock distribuito PostgreSQL (un solo PC esegue la sincronizzazione per tutti)."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #555; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(lbl_desc)

        # Box Credenziali
        box_auth = QGroupBox("Credenziali di Accesso")
        box_auth.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_layout = QFormLayout(box_auth)

        self.txt_username = QLineEdit(self.settings.get_bkode_username() or "ma002")
        self.txt_username.setPlaceholderText("Es. ma002")
        form_layout.addRow("Nome Utente:", self.txt_username)

        self.txt_password = QLineEdit(self.settings.get_bkode_password() or "")
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Password portale B-Kode")
        form_layout.addRow("Password:", self.txt_password)

        self.txt_cookie = QLineEdit(self.settings.get_bkode_cookie() or "")
        self.txt_cookie.setPlaceholderText("Opzionale (utilizzato come fallback o sessione temporanea)")
        form_layout.addRow("Cookie ci_session:", self.txt_cookie)

        layout.addWidget(box_auth)

        # Box Periodicità
        box_timer = QGroupBox("Automazione & Concorrenza")
        box_timer.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_timer = QFormLayout(box_timer)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 1440)
        self.spin_interval.setValue(self.settings.get_bkode_sync_interval())
        self.spin_interval.setSuffix(" minuti")
        form_timer.addRow("Intervallo di controllo:", self.spin_interval)

        layout.addWidget(box_timer)

        # Barra Azioni di Test e Sincronizzazione
        box_actions = QHBoxLayout()
        self.btn_test = QPushButton("🔍 Test Connessione")
        self.btn_test.setStyleSheet("padding: 6px 12px; font-weight: bold;")
        self.btn_test.clicked.connect(self._test_connection)
        box_actions.addWidget(self.btn_test)

        self.btn_sync_now = QPushButton("⚡ Sincronizza Ora")
        self.btn_sync_now.setStyleSheet("padding: 6px 12px; font-weight: bold; background-color: #E8F5E9; color: #2E7D32;")
        self.btn_sync_now.clicked.connect(self._force_sync)
        box_actions.addWidget(self.btn_sync_now)

        layout.addLayout(box_actions)

        # Etichetta Stato / Risultato
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #666; margin: 4px;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # Pulsanti Salva / Annulla
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Chiudi")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Salva Impostazioni")
        btn_save.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        btn_save.clicked.connect(self._save_settings)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _save_settings(self):
        self.settings.set_bkode_username(self.txt_username.text().strip())
        self.settings.set_bkode_password(self.txt_password.text())
        self.settings.set_bkode_cookie(self.txt_cookie.text().strip())
        self.settings.set_bkode_sync_interval(self.spin_interval.value())
        QMessageBox.information(self, "Impostazioni Salvate", "Le impostazioni di integrazione con B-Kode sono state salvate.")
        self.accept()

    def _test_connection(self):
        user = self.txt_username.text().strip()
        pwd = self.txt_password.text()
        cookie = self.txt_cookie.text().strip()

        if not pwd and not cookie:
            QMessageBox.warning(self, "Dati Mancanti", "Inserisci la password di B-Kode oppure un cookie di sessione valido per eseguire il test.")
            return

        self.btn_test.setEnabled(False)
        self.lbl_status.setText("⏳ Verifica connessione con bkode.cloud in corso...")

        self.test_thread = TestConnectionThread(user, pwd, cookie, self)
        self.test_thread.finished.connect(self._on_test_finished)
        self.test_thread.start()

    def _on_test_finished(self, ok: bool, message: str):
        self.btn_test.setEnabled(True)
        self.lbl_status.setText("")
        if ok:
            QMessageBox.information(self, "Connessione B-Kode Riuscita", message)
        else:
            QMessageBox.critical(self, "Errore Connessione B-Kode", message)

    def _force_sync(self):
        # Prima salva temporaneamente le credenziali
        self.settings.set_bkode_username(self.txt_username.text().strip())
        self.settings.set_bkode_password(self.txt_password.text())
        self.settings.set_bkode_cookie(self.txt_cookie.text().strip())

        self.btn_sync_now.setEnabled(False)
        self.lbl_status.setText("⏳ Sincronizzazione B-Kode forzata in corso... Attendere.")

        self.sync_thread = ForceSyncThread(self)
        self.sync_thread.finished.connect(self._on_sync_finished)
        self.sync_thread.start()

    def _on_sync_finished(self, result: dict):
        self.btn_sync_now.setEnabled(True)
        self.lbl_status.setText("")
        if result.get("executed"):
            msg = (
                f"Sincronizzazione completata con successo!\n\n"
                f"• Listini Prezzi sincronizzati: {result.get('price_lists_synced', 0)}\n"
                f"• Voci Articolo Listino aggiornate: {result.get('price_items_synced', 0)}\n"
                f"• Nuovi Articoli a catalogo: {result.get('products_synced', 0)}\n"
                f"• Nuove Fatture rilevate: {result.get('invoices_synced', 0)}"
            )
            QMessageBox.information(self, "Sincronizzazione B-Kode Completata", msg)
            self.sync_requested.emit()
        else:
            reason = result.get("reason") or "Errore sconosciuto"
            QMessageBox.warning(self, "Sincronizzazione Non Eseguita", f"La sincronizzazione non è stata completata:\n{reason}")
