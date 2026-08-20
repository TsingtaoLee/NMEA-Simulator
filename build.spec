# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = []
binaries = []
hiddenimports = []

for pkg in ['flask_socketio', 'engineio', 'socketio', 'simple_websocket', 'werkzeug']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ('static', 'static'),
    ('templates', 'templates'),
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['eventlet', 'eventlet.hubs', 'eventlet.hubs.kqueue'],
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
    name='NMEA-Simulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon=None,
)
