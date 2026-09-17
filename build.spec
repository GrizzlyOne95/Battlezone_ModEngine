# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files

version_file = 'branding/version_info.txt' if os.path.exists('branding/version_info.txt') else None

datas = [
    ('BGM.ttf', '.'),
    ('bz2.png', '.'),
    ('bz98.png', '.'),
    ('BZONE.ttf', '.'),
    ('branding/app_icon.ico', 'branding'),
    ('branding/app_icon.png', 'branding'),
    ('INSTALL_LINUX_GOG.md', '.'),
    ('LICENSE', '.'),
    ('README.md', '.')
]
datas += collect_data_files('tkinterdnd2')

a = Analysis(
    ['cmd.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PIL'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['branding/pyinstaller_icon_hook.py'],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BZModEngine',
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
    icon='branding/app_icon.ico',
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BZModEngine',
)
