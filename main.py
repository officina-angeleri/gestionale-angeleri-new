import sys
import os
from PyQt6.QtWidgets import QApplication, QDialog
from app.controllers.invoice_manager import InvoiceManager
from app.ui.main_window import MainWindow
from app.ui.db_selector import DatabaseSelector
from app.utils.settings import SettingsManager
from app.database import init_db

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    
    settings = SettingsManager()
    db_path = settings.get_db_path()
    remember = settings.should_remember_db()
    
    # Se non c'è un percorso salvato o non abbiamo chiesto di ricordare,  apri il selettore
    if not db_path or not remember:
        selector = DatabaseSelector(db_path, remember)
        if selector.exec() == QDialog.DialogCode.Accepted:
            db_path, remember = selector.get_result()
            settings.set_db_path(db_path)
            settings.set_remember_db(remember)
        else:
            sys.exit(0)
            
    # Verifica che il percorso sia nel formato  sqlite://
    if db_path and not db_path.startswith("sqlite:///"):
        # Se è un percorso assoluto Windows (es. C:\), servono 3 slash o 4 se su driver differente?
        # Solitamente sqlite:///C:/percorso/file.db funziona.
        connection_string = f"sqlite:///{os.path.abspath(db_path).replace('\\', '/')}"
    else:
        connection_string = db_path or "sqlite:///invoices.db"

    # Setup DB
    init_db(connection_string)
    
    # Init Logic
    controller = InvoiceManager()
    
    # Init UI
    window = MainWindow(controller)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
