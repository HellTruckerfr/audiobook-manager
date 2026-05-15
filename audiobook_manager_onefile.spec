# -*- mode: python ; coding: utf-8 -*-
#
# Build  : python -m PyInstaller audiobook_manager_onefile.spec -y
# Output : dist/AudiobookManager-portable.exe
#
# FFmpeg requis au moment du BUILD uniquement (pas chez l'utilisateur final) :
# utiliser le build FULL de gyan.dev pour libfdk_aac
# https://www.gyan.dev/ffmpeg/builds/ → ffmpeg-release-full.7z
# Extraire et mettre à jour FFMPEG_BIN ci-dessous si le chemin diffère.

FFMPEG_BIN = 'C:/ffmpeg/bin'

import glob
_icon_icos = [(f.replace('\\', '/'), 'assets/icons') for f in glob.glob('assets/icons/*.ico')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (f'{FFMPEG_BIN}/ffmpeg.exe',  'bin'),
        (f'{FFMPEG_BIN}/ffprobe.exe', 'bin'),
    ],
    datas=_icon_icos,
    hiddenimports=['PyQt6.sip'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'test'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='AudiobookManager-portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    icon='assets/icons/audiobook-manager.ico',
)
