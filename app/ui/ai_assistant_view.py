import html
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, 
    QPlainTextEdit, QPushButton, QLabel, QComboBox, 
    QDialog, QLineEdit, QFormLayout, QMessageBox, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent

from app.utils.ai_assistant import GeminiAssistant
from app.utils.voice_service import VoiceListeningDialog
from app.utils.settings import SettingsManager

def md_to_html(md_text: str) -> str:
    """Converte markdown in HTML con tabelle, codice ed elenchi, aggiungendo link per le fatture."""
    import re

    # 1. Se una riga di tabella contiene Data (gg/mm/aaaa) e Numero Fattura ma non ha ancora un link, aggiungilo
    def link_table_invoice(m):
        d_full = m.group(1)
        yr = m.group(2)
        inv_n = m.group(3).strip()
        # Se è già un link o contiene caratteri non numerici / lettere tipiche
        if '[' in inv_n or ']' in inv_n or 'fattura' in inv_n.lower():
            return m.group(0)
        return f"| {d_full} | [Fattura {inv_n} 📄](app:invoice:sale:{inv_n}:{yr}) |"

    p_tbl = r'\|\s*(\d{1,2}/\d{1,2}/(20\d{2}))\s*\|\s*([0-9A-Za-z/_-]{1,15})\s*\|'
    processed_md = re.sub(p_tbl, link_table_invoice, md_text)

    try:
        import markdown
        return markdown.markdown(processed_md, extensions=['tables', 'fenced_code'])
    except Exception:
        # Fallback semplice se libreria markdown non disponibile
        escaped = html.escape(processed_md)
        escaped = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escaped)
        escaped = re.sub(r'\*(.*?)\*', r'<i>\1</i>', escaped)
        escaped = escaped.replace('\n', '<br>')
        return escaped

class GeminiWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, assistant: GeminiAssistant, prompt: str, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.prompt = prompt

    def run(self):
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.assistant.send_message, self.prompt)
                try:
                    response = future.result(timeout=90)  # 90 secondi max
                    self.finished.emit(response)
                except concurrent.futures.TimeoutError:
                    self.error.emit(
                        "⏱️ **Timeout: Gemini non ha risposto entro 90 secondi.**\n\n"
                        "Il database potrebbe essere lento o la connessione al server Synology è interrotta. "
                        "Riprova tra qualche istante o riavvia il programma."
                    )
        except Exception as e:
            self.error.emit(str(e))

class ChatInputEdit(QPlainTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        # Invio invia il messaggio, Shift+Invio va a capo
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.send_requested.emit()
                return
        super().keyPressEvent(event)

class APIKeyDialog(QDialog):
    def __init__(self, current_key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Google Gemini API Key")
        self.resize(480, 200)
        self.setup_ui(current_key)

    def setup_ui(self, current_key: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        info_label = QLabel(
            "<b>Inserisci la tua API Key di Google Gemini</b><br>"
            "<span style='color: #64748B; font-size: 11px;'>"
            "Puoi ottenerne una gratuitamente in pochi secondi su "
            "<a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>. "
            "La chiave viene salvata localmente in modo sicuro."
            "</span>"
        )
        info_label.setOpenExternalLinks(True)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        self.input_key = QLineEdit()
        self.input_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_key.setText(current_key)
        self.input_key.setPlaceholderText("AIzaSy...")
        self.input_key.setFixedHeight(34)
        form.addRow("API Key:", self.input_key)

        layout.addLayout(form)

        # Pulsante mostra/nascondi
        btn_toggle = QPushButton("Mostra / Nascondi caratteri")
        btn_toggle.setFlat(True)
        btn_toggle.setStyleSheet("color: #1976D2; text-align: left; font-size: 11px;")
        btn_toggle.clicked.connect(self._toggle_echo)
        layout.addWidget(btn_toggle)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Salva Chiave")
        btn_save.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _toggle_echo(self):
        if self.input_key.echoMode() == QLineEdit.EchoMode.Password:
            self.input_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.input_key.setEchoMode(QLineEdit.EchoMode.Password)

    def get_api_key(self) -> str:
        return self.input_key.text().strip()

class AIAssistantWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.assistant = GeminiAssistant(controller)
        self.worker = None
        self.chat_history_html = ""
        self.setup_ui()
        self._init_welcome_message()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        # 1. BARRA SUPERIORE: Titolo, Selettore Modello, Configurazione API Key
        top_layout = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("🤖 Assistente AI Officina Angeleri")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        subtitle = QLabel("Analisi intelligente ricambi, prezzi d'acquisto fornitori, listini e codici comparativi storici.")
        subtitle.setStyleSheet("color: #64748B; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        # Selettore Modello
        top_layout.addWidget(QLabel("Modello:"))
        self.combo_model = QComboBox()
        self.combo_model.setFixedHeight(34)
        self.combo_model.addItem("Gemini Flash (Consigliato - Veloce e Gratuito)", "gemini-flash-latest")
        self.combo_model.addItem("Gemini Flash Lite", "gemini-2.5-flash-lite")
        self.combo_model.addItem("Gemini 3.6 Flash", "gemini-3.6-flash")
        cur_model = self.assistant.model_name
        idx = self.combo_model.findData(cur_model)
        if idx >= 0:
            self.combo_model.setCurrentIndex(idx)
        else:
            self.combo_model.setCurrentIndex(0)
        self.combo_model.currentIndexChanged.connect(self._on_model_changed)
        top_layout.addWidget(self.combo_model)

        # Tasto Imposta API Key
        btn_key = QPushButton("⚙️ Imposta API Key")
        btn_key.setFixedHeight(34)
        btn_key.clicked.connect(self._open_api_key_dialog)
        top_layout.addWidget(btn_key)

        # Tasto Pulisci Chat
        btn_clear = QPushButton("🗑️ Nuova Chat")
        btn_clear.setFixedHeight(34)
        btn_clear.clicked.connect(self._clear_chat)
        top_layout.addWidget(btn_clear)

        layout.addLayout(top_layout)

        # 2. PILLOLE DI SUGGERIMENTO RAPIDO
        suggestions_layout = QHBoxLayout()
        suggestions_layout.setSpacing(8)
        lbl_sug = QLabel("Domande frequenti:")
        lbl_sug.setStyleSheet("color: #64748B; font-size: 11px; font-weight: bold;")
        suggestions_layout.addWidget(lbl_sug)

        pills = [
            ("🔍 Prezzi rullo morbido e motore Carpanelli", "Cerca i prezzi del rullo morbido 3150 e del motore trifase Carpanelli, indicando fornitore, costo e listino."),
            ("🏭 Top 5 fornitori per spesa", "Chi sono i nostri primi 5 fornitori per spesa totale e quanto abbiamo pagato complessivamente?"),
            ("🔄 Corrispondenza codice legacy 3150-73", "A quale codice master corrisponde il vecchio codice 3150-73 e quali sono i prezzi?"),
            ("📦 Articoli forniti da Alusic", "Quali articoli acquistiamo da ALUSIC S.r.l. e con quali prezzi?")
        ]

        for label_text, prompt_text in pills:
            btn = QPushButton(label_text)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #F1F5F9;
                    color: #334155;
                    border: 1px solid #CBD5E1;
                    border-radius: 14px;
                    padding: 3px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #E2E8F0;
                    border-color: #94A3B8;
                }
            """)
            btn.clicked.connect(lambda _, p=prompt_text: self._send_prompt(p))
            suggestions_layout.addWidget(btn)

        suggestions_layout.addStretch()
        layout.addLayout(suggestions_layout)

        # 3. AREA CHAT
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        # IMPORTANTE: impedisce al QTextBrowser di "navigare" al link cliccato (app:invoice:...)
        # che azzererebbe il contenuto della chat. Il click viene gestito solo da anchorClicked.
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._handle_link_clicked)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #FAFAFA;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 15px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.browser, stretch=1)

        # 4. AREA DI INPUT CON TASTO VOCE E INVIO
        input_box = QVBoxLayout()
        input_box.setSpacing(6)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_text = ChatInputEdit()
        self.input_text.setPlaceholderText("Scrivi una domanda sui ricambi o premi '🎙️ VOCE' per dettare (es. 'Cerca i prezzi del rullo 3150 e della pinza ER32')...")
        self.input_text.setFixedHeight(65)
        self.input_text.setStyleSheet("""
            QPlainTextEdit {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                background-color: #FFFFFF;
            }
            QPlainTextEdit:focus {
                border: 1px solid #1976D2;
            }
        """)
        self.input_text.send_requested.connect(self._handle_send)
        input_row.addWidget(self.input_text, stretch=1)

        # Tasto VOCE (Dettatura vocale con microfono)
        self.btn_voice = QPushButton("🎙️ VOCE")
        self.btn_voice.setFixedHeight(65)
        self.btn_voice.setFixedWidth(100)
        self.btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice.setStyleSheet("""
            QPushButton {
                background-color: #E65100;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.btn_voice.clicked.connect(self._handle_voice_input)
        input_row.addWidget(self.btn_voice)

        # Tasto INVIA
        self.btn_send = QPushButton("Invia 🚀")
        self.btn_send.setFixedHeight(65)
        self.btn_send.setFixedWidth(100)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.btn_send.clicked.connect(self._handle_send)
        input_row.addWidget(self.btn_send)

        input_box.addLayout(input_row)

        # Barra di stato con opzione invio automatico
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Pronto per le domande.")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 11px;")
        status_row.addWidget(self.lbl_status, stretch=1)

        self.cb_auto_send = QCheckBox("Invia subito dopo la voce")
        self.cb_auto_send.setChecked(False)
        self.cb_auto_send.setStyleSheet("color: #475569; font-size: 11px;")
        self.cb_auto_send.setToolTip("Se attivo, la domanda viene inviata automaticamente al termine della dettatura. Se disattivo, il testo viene inserito nel riquadro per consentirti di leggerlo o correggerlo.")
        status_row.addWidget(self.cb_auto_send)

        input_box.addLayout(status_row)
        layout.addLayout(input_box)

    def _init_welcome_message(self):
        welcome_md = (
            "### 👋 Benvenuto nell'Assistente AI di Officina Angeleri!\n\n"
            "Sono collegato in tempo reale al database centrale del server Synology (`angeleri_db`). "
            "Posso aiutarti a:\n"
            "- **Confrontare più ricambi in un'unica richiesta** (es. *'Cerca i prezzi di questo ricambio, poi quell'altro e poi un altro ancora'*).\n"
            "- **Trovare le corrispondenze** tra vecchi codici da esploso macchina (es. `3150-12`) e i nuovi codici interni Angeleri (`A...` per acquisti, `L...` per lavorazioni).\n"
            "- **Verificare lo storico acquisti fornitore** (data, numero fattura e prezzo effettivo pagato).\n"
            "- **Verificare lo storico vendite clienti** degli ultimi 7 anni.\n\n"
            "💬 *Puoi scrivere nel riquadro sottostante oppure premere **🎙️ VOCE** per dettare direttamente dal microfono dell'officina.*"
        )
        self._append_message("assistant", welcome_md)

    def _append_message(self, sender: str, text: str):
        html_content = md_to_html(text)
        
        # Stile CSS moderno con tabelle ben impaginate e link interattivi
        table_style = """
            <style>
                table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 12px; }
                th, td { border: 1px solid #CBD5E1; padding: 6px 10px; text-align: left; }
                th { background-color: #F1F5F9; color: #1E293B; font-weight: bold; }
                tr:nth-child(even) { background-color: #F8FAFC; }
                code { background-color: #E2E8F0; padding: 2px 5px; border-radius: 3px; font-size: 12px; font-family: monospace; }
                b { color: #0F172A; }
                a {
                    color: #0284C7;
                    font-weight: bold;
                    text-decoration: underline;
                }
                a:hover {
                    color: #0369A1;
                    background-color: #E0F2FE;
                    border-radius: 3px;
                }
            </style>
        """

        if sender == "user":
            bubble = (
                f"<div style='margin: 12px 0 12px 80px; text-align: right;'>"
                f"<div style='display: inline-block; background-color: #1976D2; color: white; "
                f"padding: 10px 15px; border-radius: 12px 12px 2px 12px; font-size: 13px; text-align: left;'>"
                f"<b>Tu:</b><br>{html.escape(text).replace(chr(10), '<br>')}"
                f"</div></div>"
            )
        else:
            bubble = (
                f"<div style='margin: 12px 80px 12px 0;'>"
                f"<div style='background-color: #FFFFFF; border: 1px solid #E2E8F0; "
                f"padding: 12px 18px; border-radius: 12px 12px 12px 2px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>"
                f"{table_style}"
                f"<span style='color: #0284C7; font-weight: bold; font-size: 13px;'>🤖 Assistente Officina Angeleri:</span><br>"
                f"<div style='margin-top: 6px; color: #334155;'>{html_content}</div>"
                f"</div></div>"
            )

        self.chat_history_html += bubble
        self.browser.setHtml(self.chat_history_html)
        # Scorri in basso
        self.browser.verticalScrollBar().setValue(self.browser.verticalScrollBar().maximum())

    def _handle_link_clicked(self, url):
        """Intercetta i click sui link della chat (apertura fatture o link web)."""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        url_str = url.toString() if hasattr(url, 'toString') else str(url)

        # Gestione link fattura interno
        if url_str.startswith("app:invoice:") or url_str.startswith("invoice:"):
            target = url_str.replace("app:invoice:", "").replace("invoice:", "").strip()
            parts = target.split(":")
            inv_type = "auto"
            inv_num = None
            inv_year = None

            if len(parts) >= 3:
                inv_type = parts[0]
                inv_num = parts[1]
                inv_year = int(parts[2]) if parts[2].isdigit() else None
            elif len(parts) == 2:
                inv_type = parts[0]
                inv_num = parts[1]
            elif len(parts) == 1:
                inv_num = parts[0]

            if hasattr(self.main_window, 'show_invoice_detail'):
                self.main_window.show_invoice_detail(
                    invoice_type=inv_type,
                    invoice_number=inv_num,
                    invoice_year=inv_year
                )
            else:
                from app.ui.invoice_detail import InvoiceDetailDialog
                self._standalone_invoice_dlg = InvoiceDetailDialog(
                    invoice_type=inv_type,
                    invoice_number=inv_num,
                    invoice_year=inv_year,
                    parent=None
                )
                self._standalone_invoice_dlg.show()
            return

        # Gestione link esploso PDF macchina
        if url_str.startswith("app:diagram:") or url_str.startswith("diagram:"):
            target = url_str.replace("app:diagram:", "").replace("diagram:", "").strip()
            if target.isdigit():
                diag, _ = self.controller.get_diagram_detail(int(target))
                if diag and diag.file_path:
                    self.controller.open_diagram_pdf(diag.file_path)
            else:
                self.controller.open_diagram_pdf(target)
            return

        # Link web esterni
        if url_str.startswith("http://") or url_str.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url_str))

    def _handle_voice_input(self):
        """Apre la finestra di ascolto microfonico per dettare la domanda."""
        dlg = VoiceListeningDialog(self)
        if dlg.exec() and dlg.recognized_text:
            text = dlg.recognized_text.strip()
            if text:
                self.input_text.setPlainText(text)
                if self.cb_auto_send.isChecked():
                    self._handle_send()
                else:
                    self.lbl_status.setText("Testo dettato inserito nel riquadro. Premi 'Invia 🚀' o modificalo.")
                    self.lbl_status.setStyleSheet("color: #2E7D32; font-weight: bold;")
                    self.input_text.setFocus()

    def _handle_send(self):
        prompt = self.input_text.toPlainText().strip()
        if not prompt:
            return

        self.input_text.clear()
        self._send_prompt(prompt)

    def _send_prompt(self, prompt: str):
        if not self.assistant.is_configured():
            self._append_message("user", prompt)
            self._append_message(
                "assistant", 
                "⚠️ **API Key di Google Gemini non ancora inserita.**\n\n"
                "Per attivare le risposte intelligenti con accesso al database, clicca sul pulsante "
                "**'⚙️ Imposta API Key'** in alto a destra e inserisci la tua chiave gratuita."
            )
            return

        self._append_message("user", prompt)
        self.btn_send.setEnabled(False)
        self.lbl_status.setText("⏳ Gemini sta consultando il database PostgreSQL di officina...")
        self.lbl_status.setStyleSheet("color: #1976D2; font-weight: bold;")

        self.worker = GeminiWorker(self.assistant, prompt)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_worker_finished(self, response_text: str):
        self._append_message("assistant", response_text)
        self.btn_send.setEnabled(True)
        self.lbl_status.setText("Pronto per la prossima domanda.")
        self.lbl_status.setStyleSheet("color: #64748B;")

    def _on_worker_error(self, error_str: str):
        self._append_message("assistant", f"❌ Si è verificato un errore: {error_str}")
        self.btn_send.setEnabled(True)
        self.lbl_status.setText("Errore durante l'elaborazione.")
        self.lbl_status.setStyleSheet("color: #DC2626;")

    def _clear_chat(self):
        self.chat_history_html = ""
        self.browser.clear()
        self.assistant.reset_chat()
        self._init_welcome_message()

    def _on_model_changed(self):
        model = self.combo_model.currentData()
        self.assistant.update_config(api_key=None, model_name=model)
        self.lbl_status.setText(f"Modello impostato su: {model}")

    def _open_api_key_dialog(self):
        dlg = APIKeyDialog(self.assistant.api_key, self)
        if dlg.exec():
            new_key = dlg.get_api_key()
            if new_key:
                self.assistant.update_config(api_key=new_key)
                QMessageBox.information(
                    self, "API Key Salvata", 
                    "La chiave Google Gemini API è stata salvata con successo!\nL'assistente è ora attivo e pronto all'uso."
                )
                self.lbl_status.setText("API Key configurata correttamente.")
            else:
                self.assistant.update_config(api_key="")
                self.lbl_status.setText("API Key rimossa.")

    def refresh_data(self):
        pass
