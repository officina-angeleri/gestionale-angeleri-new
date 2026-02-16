from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QCheckBox)
from PyQt6.QtCore import Qt
import os

class DatabaseSelector(QDialog):
    def __init__(self, current_path=None, remember=False):
        super().__init__()
        self.setWindowTitle("Configurazione Database")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Seleziona il file del database (.db) per l'analisi:"))
        
        file_layout = QHBoxLayout()
        self.path_edit = QLineEdit(current_path or os.path.join(os.getcwd(), "invoices.db"))
        file_layout.addWidget(self.path_edit)
        
        btn_browse = QPushButton("Sfoglia...")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(btn_browse)
        
        layout.addLayout(file_layout)
        
        self.check_remember = QCheckBox("Memorizza questa scelta per i prossimi avvii")
        self.check_remember.setChecked(remember)
        layout.addWidget(self.check_remember)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Conferma")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("Esci")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona Database", os.getcwd(), "Database Files (*.db);;All Files (*)"
        )
        if file_path:
            self.path_edit.setText(file_path)

    def get_result(self):
        return self.path_edit.text(), self.check_remember.isChecked()
