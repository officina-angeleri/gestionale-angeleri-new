from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QFileDialog, 
                             QListWidget, QLabel, QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class ImportThread(QThread):
    progress_update = pyqtSignal(int, int) # current, total
    log_update = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, controller, files):
        super().__init__()
        self.controller = controller
        self.files = files
        
    def run(self):
        total = len(self.files)
        for i, f in enumerate(self.files):
            try:
                self.controller.import_invoice(f)
                self.log_update.emit(f"OK: {f}")
            except Exception as e:
                self.log_update.emit(f"ERROR {f}: {e}")
            self.progress_update.emit(i+1, total)
        self.finished_signal.emit()

class ImportDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Importa Fatture")
        self.resize(500, 400)
        
        layout = QVBoxLayout()
        
        self.btn_select = QPushButton("Seleziona File (HTML, PDF...)")
        self.btn_select.clicked.connect(self.select_files)
        layout.addWidget(self.btn_select)
        
        self.btn_select_dir = QPushButton("Seleziona Cartella (Import Massivo)")
        self.btn_select_dir.clicked.connect(self.select_directory)
        layout.addWidget(self.btn_select_dir)
        
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)
        
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        
        self.btn_start = QPushButton("Avvia Importazione")
        self.btn_start.clicked.connect(self.start_import)
        self.btn_start.setEnabled(False)
        layout.addWidget(self.btn_start)
        
        self.log_list = QListWidget()
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.log_list)
        
        self.setLayout(layout)
        self.selected_files = []
        
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Seleziona Fatture", 
            "", 
            "Fatture (*.xml *.htm *.html *.pdf *.xlsx *.csv)"
        )
        if files:
            self.selected_files = files
            self.update_list()

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Seleziona Cartella Fatture")
        if directory:
            import glob
            import os
            self.selected_files = []
            # Recursive search for supported extensions
            # Per ora supportiamo solo html/htm. In futuro pdf, xlsx...
            # Aggiungo patterns
            patterns = ['*.xml', '*.htm', '*.html', '*.pdf', '*.xlsx', '*.csv']
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if any(file.lower().endswith(ext.replace('*', '')) for ext in patterns):
                        self.selected_files.append(os.path.join(root, file))
            
            self.update_list()

    def update_list(self):
        self.file_list.clear()
        self.file_list.addItems(self.selected_files)
        self.btn_start.setEnabled(len(self.selected_files) > 0)
            
    def start_import(self):
        self.btn_select.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.log_list.clear()
        
        self.thread = ImportThread(self.controller, self.selected_files)
        self.thread.progress_update.connect(self.update_progress)
        self.thread.log_update.connect(self.append_log)
        self.thread.finished_signal.connect(self.import_finished)
        self.thread.start()
        
    def update_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        
    def append_log(self, text):
        self.log_list.addItem(text)
        self.log_list.scrollToBottom()
        
    def import_finished(self):
        QMessageBox.information(self, "Completato", "Processo di importazione terminato.")
        self.btn_select.setEnabled(True)
        self.accept() # Close dialog? Or just let user close
