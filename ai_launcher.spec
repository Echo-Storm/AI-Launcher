# ai_launcher.spec — PyInstaller build spec (--onedir)
#
# Used for BOTH the CPU-only and CUDA release variants — this file never
# changes between them. The only difference is which `torch` wheel is
# installed in the build venv *before* this spec runs (see
# .github/workflows/build.yml's matrix); PyInstaller just collects whatever
# torch build it finds, CUDA DLLs and all.
#
# --onedir, not --onefile: this app bundles torch/diffusers/transformers —
# multi-gigabyte payload. --onefile re-extracts that entire payload to a
# fresh temp directory on every single launch, which is both slow and (per
# constants.py's APP_DIR logic) would break config.json/prefs persistence,
# since a temp extraction dir is not a stable location. --onedir extracts
# once at build time; the resulting folder is what gets zipped for release.
#
# torch/transformers/diffusers/accelerate/peft/safetensors all call
# importlib.metadata.version(...) on themselves (and each other) at import
# time to check version compatibility — PyInstaller's static analysis does
# NOT bundle .dist-info metadata by default, so without copy_metadata below
# the packaged app fails at launch with PackageNotFoundError even though
# every module imported fine. This is the single most common PyInstaller +
# ML-library packaging failure; collect_all alone does not fix it.

from PyInstaller.utils.hooks import collect_all, copy_metadata

block_cipher = None

_HEAVY_PACKAGES = [
    "torch", "diffusers", "transformers", "accelerate",
    "peft", "safetensors", "spandrel",
]

_METADATA_ONLY_PACKAGES = [
    # Checked via importlib.metadata by the packages above at runtime, but
    # not necessarily import-scanned as a submodule dependency themselves —
    # if a fresh PackageNotFoundError shows up for some other dependency at
    # runtime, add it here.
    "tokenizers", "huggingface-hub", "regex", "filelock",
    "packaging", "pyyaml", "numpy", "requests", "tqdm",
]

datas = [("assets", "assets")]
binaries = []
hiddenimports = []

for _pkg in _HEAVY_PACKAGES:
    _datas, _binaries, _hiddenimports = collect_all(_pkg)
    datas += _datas
    binaries += _binaries
    hiddenimports += _hiddenimports

for _pkg in _METADATA_ONLY_PACKAGES:
    datas += copy_metadata(_pkg)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unused PyQt6 submodules — cuts dead weight the same way TorBox
        # Manager's build does, though it barely moves the needle against
        # torch's own footprint here.
        "PyQt6.QtBluetooth", "PyQt6.QtDBus", "PyQt6.QtDesigner",
        "PyQt6.QtHelp", "PyQt6.QtMultimedia", "PyQt6.QtOpenGL",
        "PyQt6.QtPdf", "PyQt6.QtPositioning", "PyQt6.QtQml",
        "PyQt6.QtQuick", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
        "PyQt6.QtSql", "PyQt6.QtSvg", "PyQt6.QtTest",
        "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtXml",
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
    [],
    exclude_binaries=True,
    name="AI_Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-compressing multi-GB CUDA DLLs costs a lot of build
                # time for little payoff and has a history of corrupting
                # some CUDA/cuDNN binaries — not worth it here.
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
    upx=False,
    upx_exclude=[],
    name="AI_Launcher",
)
