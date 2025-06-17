# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import customtkinter

block_cipher = None

# --- Descoberta Automática de Ficheiros ---
# Encontra o caminho para a pasta do customtkinter para incluir os temas
customtkinter_path = os.path.dirname(customtkinter.__file__)


datas = [
    (customtkinter_path, 'customtkinter/'),
    ('icon.ico', '.') 
]

# --- Análise Principal ---
a = Analysis(
    ['downloader_pc.py'],
    pathex=[],
    binaries=[],
    datas=datas, 
    hiddenimports=[],
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

# --- Construção do Executável (.exe) ---
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YouTubeDownloaderPro',
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
    icon='icon.ico' # Define o ícone do ficheiro
)

# --- Coleta de Ficheiros Finais ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YouTubeDownloaderPro',
)
