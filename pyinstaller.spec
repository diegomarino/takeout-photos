# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building takeout-photos macOS binary.

This bundles the Python application with exiftool and its Perl libraries
into a standalone executable that requires no external dependencies.

Build command:
    python scripts/get_exiftool.py  # Download exiftool first
    pyinstaller pyinstaller.spec     # Build the binary

Output:
    dist/takeout-photos (standalone executable)
"""

block_cipher = None

a = Analysis(
    ['src/takeout_photos/__main__.py'],  # Entry point
    pathex=[],
    binaries=[],
    datas=[
        # Bundle exiftool executable and Perl library modules
        ('build/exiftool/exiftool', '.'),  # exiftool at bundle root
        ('build/exiftool/lib', 'lib'),     # Perl modules in lib/
    ],
    hiddenimports=[
        # Explicitly include all takeout_photos modules
        'takeout_photos.cli',
        'takeout_photos.cli.commands',
        'takeout_photos.cli.main',
        'takeout_photos.core',
        'takeout_photos.core.config',
        'takeout_photos.core.constants',
        'takeout_photos.core.database',
        'takeout_photos.core.pipeline',
        'takeout_photos.stages',
        'takeout_photos.stages.extract',
        'takeout_photos.stages.validate',
        'takeout_photos.stages.metadata',
        'takeout_photos.stages.hash',
        'takeout_photos.stages.organize',
        'takeout_photos.stages.qc',
        'takeout_photos.takeout',
        'takeout_photos.takeout.json_finder',
        'takeout_photos.takeout.json_parser',
        'takeout_photos.exif',
        'takeout_photos.exif.operations',
        'takeout_photos.exif.format_detection',
        'takeout_photos.exif.validation',
        'takeout_photos.hashing',
        'takeout_photos.hashing.hasher',
        'takeout_photos.utils',
        'takeout_photos.utils.cleanup',
        'takeout_photos.utils.dependencies',
        'takeout_photos.utils.logging_setup',
        'takeout_photos.utils.progress',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test modules from bundle
        'tests',
        'pytest',
        'unittest',
    ],
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
    name='takeout-photos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress binary to reduce size
    upx_exclude=[],
    runtime_tmpdir='~/.cache/takeout-photos',  # Persist across runs; re-extracts only on update
    console=True,  # CLI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
