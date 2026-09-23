import PyInstaller.__main__
import os
import shutil
from datetime import datetime

# Configurazione Percorsi Server
SERVER_RELEASE_PATH = r"\\angeleri_new\Pubblica\Database\Antigravity\dist\versions"
SERVER_MAIN_APP_PATH = r"\\angeleri_new\Pubblica\Database\GestionaleAngeleri"

def build(one_file=False):
    version = datetime.now().strftime("%Y%m%d_%H%M")
    mode_str = "FILE UNICO" if one_file else "CARTELLA (ONEDIR)"
    print(f"=== INIZIO COMPILAZIONE GESTIONALE ANGELERI v{version} ({mode_str}) ===")
    
    # Rimuovi cartelle di build temporanee
    for folder in ['build', 'dist/temp_build']:
        if os.path.exists(folder):
            print(f"Pulizia cartella temporanea {folder}...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Avviso pulizia {folder}: {e}")

    params = [
        'main.py',
        '--onefile' if one_file else '--onedir',
        '--windowed',
        '--name=GestionaleAngeleri',
        '--clean',
        '--noconfirm',
        '--distpath=dist/temp_build',
        '--add-data=app;app',
        '--hidden-import=psycopg2',
        '--hidden-import=psycopg2._psycopg',
        '--hidden-import=sqlalchemy.dialects.postgresql',
        '--hidden-import=sqlalchemy.dialects.postgresql.psycopg2',
        '--hidden-import=google.genai',
        '--hidden-import=speech_recognition',
        '--hidden-import=pdfplumber',
        '--hidden-import=pypdfium2',
        '--hidden-import=openpyxl',
        '--hidden-import=typing_extensions',
        '--hidden-import=anyio',
        '--exclude-module=tkinter',
    ]

    print("Esecuzione PyInstaller...")
    PyInstaller.__main__.run(params)
    
    # Organizzazione versione locale
    local_version_dir = f"dist/versions/GestionaleAngeleri_v{version}"
    if not os.path.exists("dist/versions"):
        os.makedirs("dist/versions")
    
    if one_file:
        local_output = f"dist/versions/GestionaleAngeleri_v{version}.exe"
        shutil.copy2("dist/temp_build/GestionaleAngeleri.exe", local_output)
    else:
        if os.path.exists(local_version_dir):
            shutil.rmtree(local_version_dir)
        shutil.move("dist/temp_build/GestionaleAngeleri", local_version_dir)
        local_output = local_version_dir
        
        # Copia settings.json preconfigurato nella cartella di release
        if os.path.exists("settings.json"):
            shutil.copy2("settings.json", os.path.join(local_output, "settings.json"))
            print("Copiato settings.json preconfigurato nella build.")
    
    print(f"\nBuild locale completata in: {local_output}")

    # --- RELEASE SUL SERVER SYNOLOGY ---
    print(f"\nSincronizzazione della release sul server Synology...")
    import subprocess
    try:
        if not os.path.exists(SERVER_RELEASE_PATH):
            os.makedirs(SERVER_RELEASE_PATH, exist_ok=True)
            
        dest_on_server = os.path.join(SERVER_RELEASE_PATH, os.path.basename(local_output))
        
        if one_file:
            shutil.copy2(local_output, dest_on_server)
        else:
            print(f"Copia archivio versione in {dest_on_server} via robocopy...")
            subprocess.run(["robocopy", local_output, dest_on_server, "/MIR", "/NFL", "/NDL", "/R:2", "/W:2"], check=False)
            
        print(f"1. Archivio versione salvato in: {dest_on_server}")
        
        # Aggiorna anche la cartella principale per l'ufficio: \\angeleri_new\Pubblica\Database\GestionaleAngeleri
        if not one_file:
            print(f"Aggiornamento applicazione server in {SERVER_MAIN_APP_PATH} via robocopy...")
            subprocess.run(["robocopy", local_output, SERVER_MAIN_APP_PATH, "/MIR", "/NFL", "/NDL", "/R:2", "/W:2"], check=False)
            print(f"2. Applicazione principale aggiornata in: {SERVER_MAIN_APP_PATH}")
            print(f"   -> Eseguibile: {os.path.join(SERVER_MAIN_APP_PATH, 'GestionaleAngeleri.exe')}")
            
        print("\n[OK] RELEASE COMPLETATA CON SUCCESSO SUL SERVER!")
    except Exception as e:
        print(f"ERRORE durante la release sul server (permessi o rete): {e}")

if __name__ == "__main__":
    build(one_file=False)
