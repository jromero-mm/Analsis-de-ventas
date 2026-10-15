# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

python_base = Path(sys.base_prefix)
tcl_root = python_base / 'tcl'
dll_root = python_base / 'DLLs'

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[
        (str(dll_root / '_tkinter.pyd'), '.'),
        (str(dll_root / 'tcl86t.dll'), '.'),
        (str(dll_root / 'tk86t.dll'), '.'),
    ],
    datas=[
        (str(tcl_root / 'tcl8.6'), '_tcl_data'),
        (str(tcl_root / 'tk8.6'), '_tk_data'),
    ],
    hiddenimports=[
        '_tkinter', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
        'tkinter.messagebox', 'tkinter.simpledialog', 'openpyxl', 'pyperclip'
    ],
    hookspath=['pyinstaller_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AnalisisVentasDemo',
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
    name='AnalisisVentasDemo',
)
