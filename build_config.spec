# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
from PyInstaller.utils.hooks import collect_data_files

# Clean any stale Python bytecode caches before every build.
# This prevents old __pycache__ folders from affecting packaging.
project_root = os.path.dirname(__file__)
for dirpath, dirnames, _ in os.walk(project_root):
    if '__pycache__' in dirnames:
        cache_path = os.path.join(dirpath, '__pycache__')
        shutil.rmtree(cache_path, ignore_errors=True)
        dirnames.remove('__pycache__')

block_cipher = None

# --- CRITICAL: Bundle Jinja2 Templates ---
# The format is ('source_path', 'destination_folder_in_exe')
bundled_datas = [
    ('src/capl_gen/templates', 'capl_gen/templates'),
]

a = Analysis(
    ['src/capl_gen/__main__.py'],          # The entry point we created
    pathex=['src'],                        # Ensure 'src' is in the Python path
    binaries=[],
    datas=bundled_datas,                   # Include our templates
    hiddenimports=[                        # Force inclusion of heavy/dynamic libraries
        'pandas',
        'openpyxl',
        'cantools',
        'lxml',
        'jinja2',
        'capl_gen.cli'
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
    name='CAPL_Gen_Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                  # Compresses the executable (requires UPX installed, otherwise ignored)
    upx_exclude=[],
    runtime_tmpdir=None,
    # --- IMPORTANT TRADEOFF ---
    # True = Shows a background console (Required for your CLI mode to output text).
    # False = Hides the console (Great for pure GUIs, but breaks CLI standard output).
    console=True,              
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/tool_icon.ico'  # Uncomment and point to an .ico file to add an app icon
)