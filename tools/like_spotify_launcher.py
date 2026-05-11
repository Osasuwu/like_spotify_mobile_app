"""PyInstaller entry script.

`python -m like_spotify` works for editable installs, but PyInstaller spec
files prefer a concrete file path. This launcher exists only to give the
.spec a target — runtime behavior is identical to `python -m like_spotify`.
"""

import sys

from like_spotify.hosts.tray import main

if __name__ == "__main__":
    sys.exit(main())
