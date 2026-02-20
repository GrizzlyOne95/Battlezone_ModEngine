# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['cmd.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('BGM.ttf', '.'),
        ('bz2.png', '.'),
        ('bz98.png', '.'),
        ('BZONE.ttf', '.'),
        ('modman.ico', '.'),
        ('file_version_info.txt', '.'),
        ('INSTALL_LINUX_GOG.md', '.'),
        ('LICENSE', '.'),
        ('README.md', '.')
    ],
    hiddenimports=['PIL', 'tkinterdnd2'],
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
    name='BZ98R_ModManager',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BZ98R_ModManager',
)
