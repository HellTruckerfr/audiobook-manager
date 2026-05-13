# -*- mode: python ; coding: utf-8 -*-
#
# Build : pyinstaller audiobook_manager.spec
# Output: dist/AudiobookManager/AudiobookManager.exe
#
# FFmpeg requis : utiliser le build FULL de gyan.dev pour libfdk_aac
# https://www.gyan.dev/ffmpeg/builds/ → ffmpeg-release-full.7z
# Extraire et mettre à jour FFMPEG_BIN ci-dessous si le chemin diffère.

FFMPEG_BIN = 'C:/ffmpeg/bin'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (f'{FFMPEG_BIN}/ffmpeg.exe',  'bin'),
        (f'{FFMPEG_BIN}/ffprobe.exe', 'bin'),
    ],
    datas=[],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='AudiobookManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AudiobookManager',
)
