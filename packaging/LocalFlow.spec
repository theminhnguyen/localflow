# PyInstaller-Spec für ein eigenständiges LocalFlow.app (Apple Silicon).
# Bauen:  .venv/bin/pyinstaller packaging/LocalFlow.spec --noconfirm --clean
# (vom Repo-Wurzelverzeichnis aus, damit "localflow" importierbar ist)

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

__version__ = "0.3.0"

# Alle Pfade absolut, relativ zur Repo-Wurzel (SPECPATH = Ordner dieser .spec)
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []

# Pakete mit Datendateien / nativen Libs komplett einsammeln
for pkg in ("mlx", "mlx_whisper", "rumps", "sounddevice", "_sounddevice_data",
            "qrcode", "PIL", "numba", "llvmlite"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Web-App (index.html, sw.js, Icons) muss neben localflow/server.py landen
datas += [(os.path.join(ROOT, "localflow", "web"), "localflow/web")]

# pyobjc-Frameworks, die wir zur Laufzeit nutzen
hiddenimports += ["objc", "Foundation", "AppKit", "Quartz", "CoreFoundation"]
hiddenimports += collect_submodules("Quartz")
hiddenimports += ["flask", "werkzeug", "jinja2", "pynput",
                  "pynput.keyboard._darwin", "pynput.mouse._darwin"]


a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # torch nur vom Gewichts-Konverter (torch_whisper) genutzt -> zur Laufzeit
    # unnötig, spart ~530MB. Ebenso schwere/ungenutzte Pakete raus.
    # torch nur vom Gewichts-Konverter genutzt (s.o.). scipy dagegen NICHT
    # ausschließen — mlx_whisper.timing braucht scipy.signal für Zeitstempel.
    excludes=["torch", "torchvision", "torchaudio",
              "mlx_whisper.torch_whisper",
              "tkinter", "PyInstaller", "pytest", "matplotlib", "IPython",
              "pandas", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="LocalFlow",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI/Menüleiste, kein Terminalfenster
    target_arch="arm64",
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="LocalFlow",
)

app = BUNDLE(
    coll,
    name="LocalFlow.app",
    icon=os.path.join(ROOT, "packaging", "LocalFlow.icns"),
    bundle_identifier="studio.minh.localflow",
    version=__version__,
    info_plist={
        "LSUIElement": True,                 # nur Menüleiste, kein Dock/App-Umschalter
        "CFBundleName": "LocalFlow",
        "CFBundleDisplayName": "LocalFlow",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHumanReadableCopyright": "MIT — Minh Nguyen",
        "NSMicrophoneUsageDescription":
            "LocalFlow wandelt deine Sprache lokal in Text um.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)
