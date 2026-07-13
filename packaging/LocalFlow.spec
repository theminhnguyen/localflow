# PyInstaller-Spec für ein eigenständiges LocalFlow.app (Apple Silicon).
# Bauen:  .venv/bin/pyinstaller packaging/LocalFlow.spec --noconfirm --clean
# (vom Repo-Wurzelverzeichnis aus, damit "localflow" importierbar ist)

from PyInstaller.utils.hooks import collect_all, collect_submodules

__version__ = "0.3.0"

datas, binaries, hiddenimports = [], [], []

# Pakete mit Datendateien / nativen Libs komplett einsammeln
for pkg in ("mlx", "mlx_whisper", "rumps", "sounddevice", "qrcode", "PIL",
            "numba", "llvmlite"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Web-App (index.html, sw.js, Icons) muss neben localflow/server.py landen
datas += [("localflow/web", "localflow/web")]

# pyobjc-Frameworks, die wir zur Laufzeit nutzen
hiddenimports += ["objc", "Foundation", "AppKit", "Quartz", "CoreFoundation"]
hiddenimports += collect_submodules("Quartz")
hiddenimports += ["flask", "werkzeug", "jinja2", "pynput",
                  "pynput.keyboard._darwin", "pynput.mouse._darwin"]


a = Analysis(
    ["packaging/launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyInstaller", "pytest", "matplotlib", "IPython"],
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
    icon="packaging/LocalFlow.icns",
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
