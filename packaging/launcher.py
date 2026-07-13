"""Einstiegspunkt für das gebündelte LocalFlow.app (PyInstaller).

freeze_support() MUSS vor allem anderen laufen: In eingefrorenen Apps starten
multiprocessing-Kindprozesse (z.B. der resource_tracker von mlx/numba) die
eigene Binary neu — freeze_support() fängt diese Aufrufe ab, sonst landen deren
Argumente in unserem argparse ("unrecognized arguments").
"""

import multiprocessing

multiprocessing.freeze_support()

from localflow.main import main

if __name__ == "__main__":
    main()
