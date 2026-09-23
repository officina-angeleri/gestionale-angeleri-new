import speech_recognition as sr
import audioop
import time
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PyQt6.QtGui import QFont

class VoiceRecognitionThread(QThread):
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    volume_signal = pyqtSignal(int)  # Livello volume 0-100 per feedback visivo

    def __init__(self, language="it-IT", parent=None):
        super().__init__(parent)
        self.language = language
        self._is_cancelled = False
        self._is_stopped = False

    def stop_speaking(self):
        """Chiamato quando l'utente preme 'Ho finito di parlare'."""
        self._is_stopped = True

    def cancel(self):
        """Chiamato quando l'utente preme 'Annulla' o chiude la finestra."""
        self._is_cancelled = True
        self._is_stopped = True

    def run(self):
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.operation_timeout = 8

        audio_data = None

        # FASE 1: ACQUISIZIONE AUDIO CON CONTROLLO DI FINE INTERLOCUZIONE
        try:
            with sr.Microphone() as source:
                if self._is_cancelled:
                    return

                self.status_signal.emit("Calibrazione rumore ambientale...")
                recognizer.adjust_for_ambient_noise(source, duration=0.4)

                if self._is_cancelled:
                    return

                self.status_signal.emit("🎙️ IN ASCOLTO... Parla pure!\n(Premi 'Ho finito' quando hai concluso)")

                seconds_per_buf = float(source.CHUNK) / source.SAMPLE_RATE
                # 2.2 secondi di pausa prima di considerare conclusa la frase in automatico
                pause_buffer_count = int(2.2 / seconds_per_buf)
                max_buffers = int(30.0 / seconds_per_buf)  # Massimo 30 secondi di registrazione

                frames = []
                has_started_speaking = False
                silent_buffers = 0

                # Soglia dinamica calcolata durante la calibrazione
                energy_threshold = max(recognizer.energy_threshold, 150)

                while not self._is_stopped and not self._is_cancelled:
                    buffer = source.stream.read(source.CHUNK)
                    if not buffer:
                        break
                    frames.append(buffer)

                    # Calcolo livello audio per volume meter
                    try:
                        energy = audioop.rms(buffer, source.SAMPLE_WIDTH)
                    except Exception:
                        energy = 0

                    # Emetti segnale volume normalizzato 0-100
                    norm_vol = min(100, int((energy / max(energy_threshold * 2, 1)) * 100))
                    self.volume_signal.emit(norm_vol)

                    if energy > energy_threshold:
                        has_started_speaking = True
                        silent_buffers = 0
                    else:
                        if has_started_speaking:
                            silent_buffers += 1
                            # Se l'utente non preme il pulsante, ma tace per oltre 2.2 secondi
                            if silent_buffers > pause_buffer_count:
                                break

                    if len(frames) >= max_buffers:
                        break

                if frames and not self._is_cancelled:
                    audio_data = sr.AudioData(b"".join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)

        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Errore microfono: {e}")
            return

        # FASE 2: TRASCRIZIONE (Microfono già rilasciato)
        if self._is_cancelled or not audio_data:
            if not self._is_cancelled and not self.error_signal:
                self.error_signal.emit("Nessuna voce rilevata.")
            return

        self.status_signal.emit("⏳ Trascrizione vocale in corso...")
        self.volume_signal.emit(0)

        try:
            text = recognizer.recognize_google(audio_data, language=self.language)
            if not self._is_cancelled and text:
                self.result_signal.emit(text.strip())
        except sr.UnknownValueError:
            if not self._is_cancelled:
                self.error_signal.emit("Non ho capito cosa hai detto. Riprova parlando più vicino al microfono.")
        except sr.RequestError as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Errore connessione trascrizione: {e}")
        except Exception as e:
            if not self._is_cancelled:
                self.error_signal.emit(f"Errore: {e}")


class VoiceListeningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dettatura Vocale - Officina Angeleri")
        self.setFixedSize(440, 240)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.recognized_text = ""
        self.success = False
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 20, 25, 20)

        self.lbl_status = QLabel("Attivazione microfono...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #E65100;")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Misuratore visivo di volume della voce
        self.vol_bar = QProgressBar()
        self.vol_bar.setRange(0, 100)
        self.vol_bar.setValue(0)
        self.vol_bar.setFixedHeight(12)
        self.vol_bar.setTextVisible(False)
        self.vol_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                background-color: #F1F5F9;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.vol_bar)

        # Pulsanti Azione
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        # Pulsante Fine Interlocuzione Manuale
        self.btn_done = QPushButton("✅ Ho finito di parlare (Trascrivi)")
        self.btn_done.setFixedHeight(44)
        self.btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.btn_done.clicked.connect(self.on_done_clicked)
        btn_layout.addWidget(self.btn_done)

        # Pulsante Annulla
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.cancel_listening)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        # Thread di ascolto
        self.thread = VoiceRecognitionThread(language="it-IT", parent=self)
        self.thread.status_signal.connect(self.on_status)
        self.thread.result_signal.connect(self.on_result)
        self.thread.error_signal.connect(self.on_error)
        self.thread.volume_signal.connect(self.on_volume)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.start()

    def on_status(self, msg):
        self.lbl_status.setText(msg)

    def on_volume(self, val):
        self.vol_bar.setValue(val)

    def on_done_clicked(self):
        """L'utente segnala esplicitamente di aver concluso la frase."""
        self.btn_done.setEnabled(False)
        self.btn_done.setText("⏳ Trascrizione in corso...")
        self.thread.stop_speaking()

    def on_result(self, text):
        self.recognized_text = text
        self.success = True
        self.lbl_status.setText(f"Trascritto: \"{text}\"")
        self.lbl_status.setStyleSheet("color: #2E7D32; font-weight: bold;")

    def on_error(self, err):
        self.lbl_status.setText(err)
        self.lbl_status.setStyleSheet("color: #D32F2F; font-size: 11px;")
        self.vol_bar.setValue(0)
        self.btn_done.setEnabled(False)
        self.btn_cancel.setText("Chiudi")

    def on_thread_finished(self):
        if self.success and self.recognized_text:
            self.accept()

    def cancel_listening(self):
        self.thread.cancel()
        self.thread.wait(600)
        self.reject()

    def closeEvent(self, event):
        self.thread.cancel()
        self.thread.wait(600)
        super().closeEvent(event)
