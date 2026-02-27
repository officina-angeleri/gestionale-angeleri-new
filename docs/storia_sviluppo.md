# Gestionale Angeleri — Storia dello Sviluppo

> Documento centrale di tracciamento per il progetto **Gestionale Angeleri (AnalisiFatture)**.
> Aggiornato: 27 Febbraio 2026 — **Versione 1.1**

---

## 1. Panoramica del Progetto

**Gestionale Angeleri** è un'applicazione desktop per l'analisi dei costi delle fatture di acquisto dell'officina Angeleri. Importa documenti elettronici SDI (XML, HTML, PDF) e consente l'analisi dei trend di prezzo per articolo/fornitore.

| Elemento | Dettaglio |
|---|---|
| **Linguaggio** | Python 3 |
| **GUI Framework** | PyQt6 |
| **Database** | SQLite (locale o NAS `//angeleri_new/Pubblica/Database/Fornitori/invoices.db`) |
| **ORM** | SQLAlchemy |
| **Importazione dati** | XML SDI (FPR12), HTML, PDF (pdfplumber) |
| **Repository** | `officina-angeleri/gestionale-angeleri` (GitHub) |
| **Branch principale** | `main` |
| **Build** | PyInstaller → `dist/versions/AnalisiFatture_vYYYYMMDD_HHMM/` |
| **Deploy server** | `\\angeleri_new\Pubblica\Database\Antigravity\dist\versions\` |

---

## 2. Struttura del Progetto

```
gestionale-angeleri/
├── main.py                  # Entry point: selezione DB → MainWindow
├── requirements.txt         # Dipendenze Python
├── build_exe.py             # Build PyInstaller + deploy NAS
├── avvia.bat                # Avvio rapido con venv locale
├── .vscode/
│   ├── launch.json          # Config debug VS Code (debugpy)
│   └── settings.json        # Interprete Python → venv
├── app/
│   ├── database.py          # Modelli ORM: Supplier, Invoice, InvoiceItem, Product
│   ├── controllers/
│   │   ├── invoice_manager.py   # Import fatture, ricerca articoli
│   │   ├── analysis_engine.py   # Calcolo trend prezzi (pandas)
│   │   └── product_matcher.py   # Normalizzazione/matching prodotti
│   ├── parsers/
│   │   ├── base.py              # ParsedInvoice, ParsedInvoiceItem
│   │   ├── xml_sdi.py           # Parser XML SDI FPR12 (namespace flessibile)
│   │   ├── html.py              # Parser HTML fatture
│   │   └── pdf.py               # Parser PDF (pdfplumber)
│   └── ui/
│       ├── main_window.py       # MainWindow + toolbar
│       ├── dashboard.py         # Statistiche: lordo/netto/conteggio/top fornitore
│       ├── analysis.py          # AnalysisWidget (trend prezzi 13 col) + HistoryDialog
│       ├── article_search.py    # Ricerca articoli con filtro fornitore
│       ├── invoice_detail.py    # InvoiceDetailDialog (testata + righe)
│       ├── reports.py           # Report aggregati per fornitore e anno
│       ├── import_dialog.py     # Import singolo file o cartella intera
│       ├── db_selector.py       # Selezione DB all'avvio
│       └── utils/
│           ├── settings.py      # SettingsManager (settings.json)
│           └── ui_utils.py      # SortableTableWidgetItem
└── docs/
    └── storia_sviluppo.md   # Questo file
```

---

## 3. Schema Database

| Tabella | Colonne chiave | Note |
|---|---|---|
| `suppliers` | `id`, `name` (unique), `piva` | Auto-creato all'import |
| `invoices` | `id`, `supplier_id` (FK), `date`, `number`, `total_amount`, `file_path` | Deduplicazione per (supplier, number, date) |
| `products` | `id`, `code`, `customer_code`, `name` (normalizzato) | Matching articoli cross-fattura |
| `invoice_items` | `id`, `invoice_id` (FK), `product_id` (FK), `code`, `customer_code`, `description`, `quantity`, `unit_price`, `total_price` | Righe di dettaglio |

---

## 4. Funzionalità Implementate

### v1.0 — Setup Iniziale
- [x] Struttura progetto e repository Git
- [x] Modelli SQLAlchemy (Supplier, Invoice, InvoiceItem, Product)
- [x] Parser XML SDI FPR12 con namespace flessibile
- [x] Parser HTML e PDF
- [x] GUI PyQt6: Dashboard, Analisi Prezzi, Report, Importa
- [x] Gestione sconti scorporati Alusic (TipoCessionePrestazione=SC)
- [x] Filtro righe tecniche (rumore SDI: righe ausiliarie, CONAI, ecc.)
- [x] Calcolo prezzo unitario reale (PrezzoTotale/Quantita al netto sconti)
- [x] `ProductMatcher`: normalizzazione codici articolo cross-fornitore
- [x] Selezione DB all'avvio con opzione "ricorda" (settings.json)
- [x] "Cambia Database" dalla toolbar con riavvio automatico

### v1.1 — 27 Febbraio 2026
- [x] **Ricerca Articoli**: aggiunto filtro per fornitore (QComboBox auto-popolato)
- [x] **Doppio click** su riga di ricerca → apre `InvoiceDetailDialog` (testata + righe)
- [x] **InvoiceDetailDialog**: nuovo dialogo con dati fattura completi e tabella righe ordinabili
- [x] **Merge fornitori duplicati**: script di normalizzazione per MATTI e ALUSIC
  - `MATTI S.r.l.` (35 fatt.) → `MATTI SRL OFFICINE MECCANICHE` (86 fatt. totali)
  - `ALUSIC S.p.a.` (8 fatt.) → `ALUSIC S.r.l.` (69 fatt. totali)
- [x] `avvia.bat`: script di avvio rapido con venv locale
- [x] `.vscode/launch.json` + `settings.json`: configurazione debug VS Code

---

## 5. Parser XML SDI — Dettaglio Tecnico

Il parser `xml_sdi.py` gestisce le specificità del formato FPR12:

| Feature | Implementazione |
|---|---|
| **Namespace flessibile** | Rilevamento automatico da `root.tag`, fallback senza namespace |
| **Sconti scorporati** | `TipoCessionePrestazione=SC` → incorporato nella riga padre |
| **Fallback sconto** | Prezzo negativo + keyword (SCONTO/ABBUONO) → incorporato |
| **Filtro rumore** | Righe con prezzo=0 + keyword tecniche → scartate |
| **Prezzo reale** | `PrezzoTotale / Quantita` (al netto degli sconti SDI) |
| **Codici articolo** | `AswArtFor`/`FORNITORE`/`MF`/`SA` → `code`; `CLIENTE`/`CU` → `customer_code` |
| **Multi-body** | Supporto fatture con più `FatturaElettronicaBody` |

---

## 6. Build e Deploy

```bash
# Dal terminale nella cartella progetto, con venv attivo:
python build_exe.py

# Output locale:
dist/versions/AnalisiFatture_vYYYYMMDD_HHMM/AnalisiFatture.exe

# Copia automatica sul server NAS:
\\angeleri_new\Pubblica\Database\Antigravity\dist\versions\
```

### Avvio locale (sviluppo)
```bash
# Metodo 1 — doppio click:
avvia.bat

# Metodo 2 — terminale:
venv\Scripts\python.exe main.py

# Metodo 3 — VS Code:
F5  (usa .vscode/launch.json)
```

---

## 7. Decisioni Progettuali

| # | Decisione | Motivazione |
|---|---|---|
| 1 | **SQLite locale/NAS** | Single-user, condivisione tramite Synology NAS |
| 2 | **PyQt6** | Framework moderno, coerente con altri progetti Angeleri |
| 3 | **Prezzo = PrezzoTotale/Qtà** | Garantisce il prezzo reale netto sconti SDI interni |
| 4 | **Product normalizzato** | Permette cross-reference dello stesso articolo tra fornitori diversi |
| 5 | **Import cartella intera** | Permette import massivo (es. 86 fatture Matti in un click) |
| 6 | **SortableTableWidgetItem** | Qt ordina tutto come testo by default; override `__lt__` per date e numeri |
| 7 | **Deduplicazione (supplier+number+date)** | Evita duplicati su re-import della stessa cartella |

---

## 8. Fornitori Gestiti

| Fornitore | Formato | Note |
|---|---|---|
| **MATTI SRL OFFICINE MECCANICHE** | XML SDI FPR12 | 86 fatture (2022–2026), codici `SPA-*`, `L040-*` |
| **ALUSIC S.r.l.** | XML SDI FPR12 | 69 fatture, sconti scorporati (SC) gestiti |
| **Carpanelli** | XML/HTML | — |
| **Sacchi** | PDF/HTML | — |
| **Comel** | XML SDI | — |
| **IMBG** | XML SDI | — |

---

## 9. Problemi Risolti

| # | Problema | Soluzione |
|---|---|---|
| 1 | Sconti Alusic come righe separate → prezzo errato | Rilevamento `TipoCessionePrestazione=SC` + fusione nella riga padre |
| 2 | Righe tecniche (rumore SDI) importate come articoli | Filtro per keyword (`riga ausiliaria`, `CONAI`, ecc.) con prezzo=0 |
| 3 | `${workspaceFolder}` errato in VS Code (workspace = `.antigravity`) | Usato percorsi assoluti in `launch.json` |
| 4 | Fornitore Matti su 2 denominazioni (`S.r.l.` vs `SRL OFFICINE`) | Script merge DB: riassegnazione fatture + rimozione duplicato |
| 5 | Fornitore Alusic su 2 denominazioni (`S.p.a.` vs `S.r.l.`) | Stesso script merge |
| 6 | Doppio click ricerca articoli apriva solo QMessageBox | Creato `InvoiceDetailDialog` completo |

---

*Aggiornato progressivamente durante lo sviluppo.*
