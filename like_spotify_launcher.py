"""PyInstaller entry target — keeps the spec workflow independent of console_scripts."""

from like_spotify.hosts.tray import main

if __name__ == "__main__":
    raise SystemExit(main())
