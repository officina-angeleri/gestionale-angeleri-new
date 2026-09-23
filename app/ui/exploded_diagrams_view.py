import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QComboBox, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QMessageBox, QFrame, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from app.utils.ui_utils import SortableTableWidgetItem

class ExplodedDiagramsWidget(QWidget):
    """
    Vista dedicata alla consultazione degli oltre 170 esplosi tecnici PDF delle macchine
    e delle relative distinte base componenti con comparazione codici vecchi e nuovi.
    """
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.main_window = parent
        self.current_diagram_id = None
        self.setup_ui()
        self.load_machine_models()
        self.load_diagrams()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        # ── Intestazione Superiore ──
        top_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("📖 Esplosi Macchine & Distinte Base")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        subtitle = QLabel("Catalogo tecnico disegni PDF, schemi di montaggio e corrispondenze codici ricambio vecchi/nuovi.")
        subtitle.setStyleSheet("color: #64748B; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        # Pulsante Sfoglia e Importa Cartella Esplosi
        btn_browse = QPushButton("📁 Sfoglia Cartella Esplosi...")
        btn_browse.setFixedHeight(36)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #F0FDF4;
                border: 1px solid #86EFAC;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: bold;
                color: #166534;
            }
            QPushButton:hover {
                background-color: #DCFCE7;
            }
        """)
        btn_browse.clicked.connect(self._handle_browse_reindex)
        top_layout.addWidget(btn_browse)

        # Pulsante Reindicizzazione Cartella Predefinita
        btn_reindex = QPushButton("🔄 Re-indicizza Default")
        btn_reindex.setFixedHeight(36)
        btn_reindex.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reindex.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 500;
                color: #334155;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """)
        btn_reindex.clicked.connect(self._handle_reindex)
        top_layout.addWidget(btn_reindex)

        # Pulsante Importa Comparativo Codici
        btn_comp = QPushButton("📑 Importa Comparativo...")
        btn_comp.setFixedHeight(36)
        btn_comp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_comp.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """)
        btn_comp.clicked.connect(self._handle_import_comparativo)
        top_layout.addWidget(btn_comp)

        layout.addLayout(top_layout)

        # ── Barra Filtri & Ricerca ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        filter_bar.addWidget(QLabel("Modello Macchina:"))
        self.combo_machines = QComboBox()
        self.combo_machines.setFixedHeight(36)
        self.combo_machines.setMinimumWidth(220)
        self.combo_machines.currentIndexChanged.connect(self.load_diagrams)
        filter_bar.addWidget(self.combo_machines)

        filter_bar.addSpacing(10)
        self.input_search = QLineEdit()
        self.input_search.setFixedHeight(36)
        self.input_search.setPlaceholderText("Cerca per codice tavola (es. M1-0002), codice master (es. L011-0096) o nome ricambio...")
        self.input_search.setStyleSheet("font-size: 13px; padding-left: 10px; border: 1px solid #CBD5E1; border-radius: 6px;")
        self.input_search.returnPressed.connect(self.load_diagrams)
        filter_bar.addWidget(self.input_search, stretch=1)

        btn_search = QPushButton("🔍 Cerca")
        btn_search.setFixedHeight(36)
        btn_search.setFixedWidth(100)
        btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_search.setStyleSheet("background-color: #1976D2; color: white; font-weight: bold; border-radius: 6px;")
        btn_search.clicked.connect(self.load_diagrams)
        filter_bar.addWidget(btn_search)

        btn_clear = QPushButton("Pulisci")
        btn_clear.setFixedHeight(36)
        btn_clear.clicked.connect(self._handle_clear_search)
        filter_bar.addWidget(btn_clear)

        layout.addLayout(filter_bar)

        # ── Splitter Centrale (Lista Esplosi a Sinistra, Dettagli e Componenti a Destra) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False) # Impedisce la chiusura automatica dei pannelli

        # --- PANNELLO SINISTRO: TABELLA ESPLOSI ---
        left_widget = QWidget()
        left_widget.setMinimumWidth(400) # Larghezza minima garantita per non essere mai schiacciato
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        lbl_list = QLabel("Tavole & Disegni Tecnici Archiviati:")
        lbl_list.setStyleSheet("color: #334155; font-weight: bold; font-size: 12px;")
        left_layout.addWidget(lbl_list)

        self.table_diagrams = QTableWidget()
        self.table_diagrams.setColumnCount(5)
        self.table_diagrams.setHorizontalHeaderLabels(["Codice", "Modello", "Titolo Disegno", "Pag.", "Distinta"])
        self.table_diagrams.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_diagrams.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_diagrams.setSortingEnabled(True)
        self.table_diagrams.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_diagrams.itemSelectionChanged.connect(self._on_diagram_selected)
        left_layout.addWidget(self.table_diagrams)

        splitter.addWidget(left_widget)

        # --- PANNELLO DESTRO: DETTAGLIO ESPLOSO & DISTINTA RICAMBI ---
        right_widget = QWidget()
        right_widget.setMinimumWidth(480)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Box Testata Esploso Selezionato
        self.box_header = QGroupBox("Tavola Selezionata")
        self.box_header.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #CBD5E1; border-radius: 8px; padding: 12px; background-color: #F8FAFC; }")
        header_layout = QHBoxLayout(self.box_header)

        info_box = QVBoxLayout()
        self.lbl_selected_title = QLabel("Seleziona una tavola dall'elenco a sinistra")
        self.lbl_selected_title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.lbl_selected_title.setStyleSheet("color: #0F172A;")
        self.lbl_selected_title.setWordWrap(True) # Va a capo e non allarga la finestra
        
        self.lbl_selected_meta = QLabel("-")
        self.lbl_selected_meta.setStyleSheet("color: #64748B; font-size: 11px;")
        self.lbl_selected_meta.setWordWrap(True)
        info_box.addWidget(self.lbl_selected_title)
        info_box.addWidget(self.lbl_selected_meta)
        header_layout.addLayout(info_box, stretch=1)

        # Tasto Grande Apri PDF
        self.btn_open_pdf = QPushButton("📄 Apri Disegno PDF a Schermo Intero")
        self.btn_open_pdf.setFixedHeight(42)
        self.btn_open_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_pdf.setEnabled(False)
        self.btn_open_pdf.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #1B5E20;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.btn_open_pdf.clicked.connect(self._open_current_pdf)
        header_layout.addWidget(self.btn_open_pdf)

        right_layout.addWidget(self.box_header)

        # Tabella Componenti
        lbl_parts = QLabel("Elenco Parti & Ricambi Associati (Doppio click per cercare il ricambio a 360°):")
        lbl_parts.setStyleSheet("color: #334155; font-weight: bold; font-size: 12px;")
        right_layout.addWidget(lbl_parts)

        self.table_items = QTableWidget()
        self.table_items.setColumnCount(5)
        self.table_items.setHorizontalHeaderLabels(["Pos. Disegno (Old)", "Codice Master", "Descrizione Ricambio", "Q.tà", "Pag. PDF"])
        self.table_items.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_items.setSortingEnabled(True)
        self.table_items.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_items.cellDoubleClicked.connect(self._on_item_double_clicked)
        right_layout.addWidget(self.table_items)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([450, 750])

        layout.addWidget(splitter, stretch=1)

        # Barra di stato inferiore
        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(self.lbl_status)

    def load_machine_models(self):
        """Carica i modelli di macchina disponibili nel selettore a tendina."""
        rows = self.controller.get_machine_models_with_counts()
        self.combo_machines.blockSignals(True)
        self.combo_machines.clear()
        
        total_diags = sum(r[1] for r in rows)
        self.combo_machines.addItem(f"Tutte le macchine ({total_diags})", userData=None)
        
        for model, count in rows:
            self.combo_machines.addItem(f"{model} ({count})", userData=model)
            
        self.combo_machines.blockSignals(False)

    def load_diagrams(self):
        """Carica l'elenco degli esplosi in base ai filtri selezionati."""
        selected_model = self.combo_machines.currentData()
        search_txt = self.input_search.text().strip()

        diagrams = self.controller.get_exploded_diagrams(machine_model=selected_model, search_text=search_txt)

        self.table_diagrams.setSortingEnabled(False)
        self.table_diagrams.setRowCount(len(diagrams))

        for row, d in enumerate(diagrams):
            # Codice
            item_code = SortableTableWidgetItem(d.code, sort_value=d.code)
            item_code.setData(Qt.ItemDataRole.UserRole, d.id)
            self.table_diagrams.setItem(row, 0, item_code)

            # Modello
            self.table_diagrams.setItem(row, 1, QTableWidgetItem(d.machine_model or "-"))

            # Titolo
            self.table_diagrams.setItem(row, 2, QTableWidgetItem(d.title))

            # Pagine
            self.table_diagrams.setItem(row, 3, SortableTableWidgetItem(str(d.pages_count), sort_value=d.pages_count))

            # Distinta presente
            has_table_str = "✅ Sì" if d.has_parts_table else "📄 Schema"
            item_table = QTableWidgetItem(has_table_str)
            if d.has_parts_table:
                item_table.setForeground(QColor("#2E7D32"))
            else:
                item_table.setForeground(QColor("#64748B"))
            self.table_diagrams.setItem(row, 4, item_table)

        self.table_diagrams.setSortingEnabled(True)
        self.lbl_status.setText(f"Trovate {len(diagrams)} tavole tecniche.")

        # Seleziona la prima riga se presente
        if len(diagrams) > 0:
            self.table_diagrams.selectRow(0)
        else:
            self._clear_details()

    def _on_diagram_selected(self):
        selected_rows = self.table_diagrams.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        item = self.table_diagrams.item(row, 0)
        if not item:
            return

        diag_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_diagram_detail(diag_id)

    def _load_diagram_detail(self, diag_id: int):
        self.current_diagram_id = diag_id
        diag, items = self.controller.get_diagram_detail(diag_id)
        if not diag:
            self._clear_details()
            return

        self.current_pdf_path = diag.file_path
        self.btn_open_pdf.setEnabled(True)

        self.lbl_selected_title.setText(f"{diag.code} — {diag.title}")
        self.lbl_selected_meta.setText(
            f"Modello: {diag.machine_model} | File: {diag.file_name} | Totale Pagine: {diag.pages_count} | Componenti indicizzati: {len(items)}"
        )

        self.table_items.setSortingEnabled(False)
        self.table_items.setRowCount(len(items))

        for row, it in enumerate(items):
            # Posizione Disegno (Old)
            pos_val = it.position_num or it.old_position_code or "-"
            item_pos = SortableTableWidgetItem(pos_val, sort_value=pos_val)
            item_pos.setData(Qt.ItemDataRole.UserRole, it.part_code)
            self.table_items.setItem(row, 0, item_pos)

            # Codice Master
            item_code = QTableWidgetItem(it.part_code or "-")
            if it.part_code:
                item_code.setForeground(QColor("#0284C7"))
                font = item_code.font()
                font.setBold(True)
                item_code.setFont(font)
            self.table_items.setItem(row, 1, item_code)

            # Descrizione
            self.table_items.setItem(row, 2, QTableWidgetItem(it.description))

            # Quantità
            self.table_items.setItem(row, 3, SortableTableWidgetItem(f"{it.quantity:.1f}", sort_value=it.quantity))

            # Pagina PDF
            self.table_items.setItem(row, 4, SortableTableWidgetItem(f"Pag. {it.page_number}", sort_value=it.page_number))

        self.table_items.setSortingEnabled(True)

    def _clear_details(self):
        self.current_diagram_id = None
        self.current_pdf_path = None
        self.btn_open_pdf.setEnabled(False)
        self.lbl_selected_title.setText("Nessun esploso selezionato")
        self.lbl_selected_meta.setText("-")
        self.table_items.setRowCount(0)

    def _open_current_pdf(self):
        try:
            if hasattr(self, 'current_pdf_path') and self.current_pdf_path:
                ok, msg = self.controller.open_diagram_pdf(self.current_pdf_path)
                if not ok:
                    QMessageBox.warning(self, "Apertura PDF", f"Impossibile aprire il file:\n{msg}")
            else:
                QMessageBox.information(self, "Apertura PDF", "Nessun percorso PDF associato alla tavola selezionata.")
        except Exception as e:
            QMessageBox.critical(self, "Errore Apertura PDF", f"Si è verificato un errore durante l'apertura del PDF:\n{e}")

    def _on_item_double_clicked(self, row, col):
        """Al doppio click su un componente, naviga automaticamente alla Ricerca 360° con quel codice."""
        item = self.table_items.item(row, 0)
        if not item:
            return
        part_code = item.data(Qt.ItemDataRole.UserRole)
        
        # Se non c'è part_code, prendi il testo della colonna 1 o la descrizione
        if not part_code:
            col1 = self.table_items.item(row, 1)
            if col1 and col1.text() != "-":
                part_code = col1.text().strip()
            else:
                part_code = self.table_items.item(row, 2).text().strip()

        if part_code and hasattr(self.main_window, 'switch_view') and hasattr(self.main_window, 'article_search'):
            # Passa alla vista Ricerca Ricambi 360° (indice 5)
            self.main_window.switch_view(5)
            # Precompila la casella di ricerca e lancia la query
            self.main_window.article_search.search_input.setText(part_code)
            self.main_window.article_search.perform_search()

    def _handle_clear_search(self):
        self.input_search.clear()
        self.combo_machines.setCurrentIndex(0)
        self.load_diagrams()

    def _handle_browse_reindex(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Seleziona Cartella contenente i PDF degli Esplosi Tecnici"
        )
        if not directory:
            return
        self._run_indexer(directory)

    def _handle_reindex(self):
        reply = QMessageBox.question(
            self, "Re-indicizzazione Esplosi PDF",
            "Vuoi ri-scansionare i file PDF nella cartella predefinita (File_per_progetto/Esplosi)?\n\n"
            "Nota: il database non perde nessun dato esistente; aggiorna o aggiunge solo i disegni trovati.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_indexer(None)

    def _run_indexer(self, folder=None):
        folder_desc = folder if folder else "cartella predefinita"
        self.lbl_status.setText(f"⏳ Indicizzazione in corso da {folder_desc}...")
        QApplication.processEvents()

        res = self.controller.reindex_all_diagrams(folder)
        if res.get('status') == 'ok':
            QMessageBox.information(self, "Indicizzazione Completata", res.get('message', 'Completato.'))
            self.load_machine_models()
            self.load_diagrams()
            self.lbl_status.setText(f"Indicizzazione completata con successo: {res.get('diagrams_indexed', 0)} tavole elaborate.")
        else:
            msg = res.get('message', 'Errore durante la scansione.')
            QMessageBox.warning(
                self, "Nessuna Modifica",
                f"{msg}\n\n"
                "🛡️ PROTEZIONE SICUREZZA:\n"
                "Il database non è stato toccato: tutti gli esplosi, i componenti e i dati esistenti sono rimasti perfettamente intatti."
            )
            self.lbl_status.setText("Operazione annullata: nessun dato modificato.")

    def _handle_import_comparativo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona File PDF Comparativo Codici (Vecchio -> Nuovo)",
            "", "Documenti PDF (*.pdf *.PDF)"
        )
        if not file_path:
            return
        self.lbl_status.setText("⏳ Importazione comparativo codici in corso...")
        QApplication.processEvents()
        res = self.controller.import_comparativo_codes(file_path)
        if res.get('status') == 'ok':
            QMessageBox.information(
                self, "Comparativo Aggiornato", 
                f"{res.get('message', 'Completato.')}\nI codici storici nel database sono stati aggiornati con successo."
            )
            self.lbl_status.setText("Comparativo codici aggiornato con successo.")
        else:
            QMessageBox.critical(self, "Errore", res.get('message', "Errore durante l'importazione."))
            self.lbl_status.setText("Errore durante l'importazione comparativo.")

    def refresh_data(self):
        self.load_machine_models()
        self.load_diagrams()
