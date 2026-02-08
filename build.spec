# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect tkinterdnd2 files if installed, otherwise empty lists
try:
    tmp_ret = collect_all('tkinterdnd2')
    datas, binaries, hiddenimports = tmp_ret
except:
    datas, binaries, hiddenimports = [], [], []

a = Analysis(
    ['cmd.py'],
    pathex=[],
    binaries=binaries,
    datas=datas + [('BZONE.ttf', '.'), ('BGM.ttf', '.'), ('bz98.png', '.'), ('bz2.png', '.'), ('modman.ico', '.')],
    hiddenimports=hiddenimports + ['PIL.Image', 'PIL.ImageTk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BZ98R_ModManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='file_version_info.txt',
    icon='modman.ico', 
)