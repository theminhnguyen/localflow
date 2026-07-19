"""LocalFlow — lokale Sprach-Diktier-App (Wispr-Flow-Nachbau, 100% offline).

WICHTIG: Diese Datei bleibt frei von schweren Imports (mlx_whisper, flask, …) —
sie ist die zentrale Versionsquelle und wird u.a. von packaging/build_dmg.sh per
"python -c 'from localflow import __version__'" gelesen, ohne dabei die ganze
App-Importkette (und damit Sekunden an Ladezeit) mitzuschleppen.
"""

__version__ = "0.6.1"
