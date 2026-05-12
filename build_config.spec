# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
from PyInstaller.utils.hooks import collect_data_files

# Clean any stale Python bytecode caches before every build.
# This prevents old __pycache__ folders from affecting packaging.
project_root = os.path.dirname('src')
for dirpath, dirnames, _ in os.walk(project_root):
    if '__pycache__' in dirnames:
        cache_path = os.path.join(dirpath, '__pycache__')
        shutil.rmtree(cache_path, ignore_errors=True)
        dirnames.remove('__pycache__')

block_cipher = None

# --- CRITICAL: Bundle Templates and GUI Images safely ---
# Destination must be relative (no leading slash) so it unpacks inside the temporary _MEIPASS folder
bundled_datas = [
    # Assuming templates are in src/templates. We unpack them to 'templates' inside the exe.
    ('src/templates', 'templates'), 
    
    # Updated to capl_bolt
    ('src/capl_bolt/gui/images', 'gui/images'), 
]

a = Analysis(
    ['src/capl_bolt/__main__.py'],         # Updated to capl_bolt
    pathex=['src'],                        
    binaries=[],
    datas=bundled_datas,                   
    hiddenimports=[                        
        'pandas',
        'openpyxl',
        'lxml',
        'jinja2',
        'PyQt6',
        'capl_bolt.cli',                   # Updated to capl_bolt
        'capl_bolt.gui.tool_gui'           # Updated to capl_bolt
    ],
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
    name='CAPLBolt',                       
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                  
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,    
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/capl_bolt/gui/images/app_icon.ico'  # Updated to capl_bolt
)