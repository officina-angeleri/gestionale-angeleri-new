# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app', 'app')],
    hiddenimports=['psycopg2', 'psycopg2._psycopg', 'sqlalchemy.dialects.postgresql', 'sqlalchemy.dialects.postgresql.psycopg2', 'google.genai', 'speech_recognition', 'pdfplumber', 'pypdfium2', 'openpyxl', 'typing_extensions', 'anyio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GestionaleAngeleri',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GestionaleAngeleri',
)
