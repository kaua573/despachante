# -*- mode: python ; coding: utf-8 -*-
#
# Build: pyinstaller despachante.spec
# Gera dist/SistemaDespachante/SistemaDespachante.exe (modo --onedir).
#
# Por que --onedir e não --onefile?
#   --onefile extrai tudo para uma pasta temporária a CADA execução, o que
#   deixa a abertura do programa nitidamente mais lenta. --onedir abre na
#   hora e ainda assim vira um único instalador amigável via Inno Setup
#   (installer.iss), que é o que o usuário final realmente vê.

from PyInstaller.utils.hooks import collect_submodules

hidden_imports = (
    collect_submodules("flask")
    + collect_submodules("flask_sqlalchemy")
    + collect_submodules("flask_login")
    + collect_submodules("flask_migrate")
    + collect_submodules("sqlalchemy")
    + collect_submodules("werkzeug")
    + collect_submodules("waitress")
    + ["reportlab", "reportlab.graphics.barcode", "openpyxl"]
)

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app/templates", "app/templates"),
        ("app/static", "app/static"),
        ("logoapp.ico", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SistemaDespachante",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # sem janela de CMD para o usuário final
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="logoapp.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SistemaDespachante",
)
