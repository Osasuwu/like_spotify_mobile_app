# Contributing

Thanks for looking! This file collects what's known to be easy to land
(good-first-PR ideas), how the desktop framework is laid out, and how
tests / CI work.

## Repo at a glance

- **Android** (`lib/`, `android/app/src/main/kotlin/…`) — Flutter + Kotlin
  app that listens for headset pause-play patterns. Feature-complete for
  Phase 0.
- **Desktop** (`like_spotify/`) — pluggable Python framework. Default
  flavor is a Windows tray host + global hotkey. Pluggability is what
  the OSS-framework refactor ([#19](https://github.com/Osasuwu/like_spotify_mobile_app/issues/19))
  is about: every concern (`Trigger`, `MusicProvider`, `Storage`,
  `PreLikeAction`, `PostLikeAction`, host) is a small interface in
  `like_spotify/core/`, and concrete implementations live under
  `like_spotify/extensions/` and `like_spotify/hosts/`.

## Desktop layout

```
like_spotify/
├── core/                 # Pure interfaces — no I/O, no platform code.
├── extensions/           # Pluggable implementations.
│   ├── spotify/                  # Spotify Web API provider (default).
│   ├── tray_hotkey_trigger/      # Global-hotkey trigger (Windows).
│   ├── one_shot_cli_trigger/     # Per-invocation trigger (every OS).
│   ├── supabase_storage/         # Default counter backend.
│   ├── google_sheets_storage/    # Sheets-backed counter (second impl).
│   ├── archive_remove/           # PostLikeAction.
│   ├── promote_to_best_of/       # PostLikeAction.
│   └── follow_artist/            # PostLikeAction (needs Storage).
└── hosts/
    ├── windows.py        # Resident tray + global hotkey + autostart.
    ├── _stub.py          # macOS / Linux CLI fallback (like-once only).
    └── _common.py        # Shared config / setup / pipeline wiring.
```

`hosts/__init__.py` picks the right host at startup via `sys.platform`.
Anything Windows-specific (`winreg`, `winsound`, `ctypes.windll`,
`pystray`) lives in `hosts/windows.py` and the `tray_hotkey_trigger`
extension — never in `core/`.

## Good-first-PR ideas

### `hosts/macos.py` — native tray host for macOS

Today macOS gets the `_stub` host: `like-spotify --setup` and
`like-spotify like-once` work; the resident tray does not. A native
macOS host would:

- Render a menu-bar icon (`rumps` is the easy path, `pyobjc` if you want
  no extra deps).
- Register a global hotkey (`pynput` works; check the accessibility
  permission flow).
- Install a Launch Agent for autostart, or print clean instructions for
  the user to copy a plist into `~/Library/LaunchAgents/` — explicit is
  fine, we don't ship a Launch Agent automatically.
- Reuse everything in `hosts/_common.py` — pipeline wiring, setup
  flow, config paths.

Mirror `hosts/windows.py` for shape; aim for ~200 LOC. Hook it up by
extending the dispatch in `hosts/__init__.py::select_host`.

### `hosts/linux.py` — Linux tray host

Same shape as macOS:

- Tray icon via `pystray` (works on common DEs with an
  `AppIndicator3`/`StatusNotifierItem` daemon — Gnome needs the
  AppIndicator extension; KDE works out of the box).
- Global hotkey — the existing `keyboard` library needs root on Linux,
  so prefer `pynput` (X11/Wayland) or document the limitation.
- Autostart via a generated `.desktop` file in
  `~/.config/autostart/`.
- Same `_common` wiring as the other hosts.

### Smaller wins

- **`Storage` impls** — anything tabular works. Already shipped:
  Supabase + Google Sheets. Wanted: SQLite (zero-config local) for users
  who don't want a cloud backend.
- **`Trigger` impls** — global hotkey is one signal source; an MQTT
  trigger or a "shake your phone" → webhook flow would be a fun second
  resident trigger.
- **`PostLikeAction` impls** — anything that wants to react to a like.
  Mood tagging, last.fm scrobble fix-up, "send to a friend's queue", etc.

## Adding an extension

1. Create `like_spotify/extensions/<your_thing>/__init__.py` with the
   concrete class and a top-level factory named after the extension
   point — `TRIGGER`, `MUSIC_PROVIDER`, `STORAGE`,
   `PRE_LIKE_ACTION`, or `POST_LIKE_ACTION`.
2. Create `manifest.json` next to it (see existing extensions for the
   schema — `domain`, `extension_point`, `name`, `description`,
   `requirements`, `stage`).
3. Register the manifest file in `pyproject.toml`'s
   `[tool.setuptools.package-data]` block.
4. Add tests under `tests/`. For `Storage`, run the shared contract
   suite from `tests/test_storage_contract.py`. For everything else,
   small async unit tests against the interface are enough.

## Running tests

```bash
pip install -e .[dev]
pytest                  # all tests
pytest tests/test_pipeline.py -k storage   # one slice
flutter test            # Android tests
```

CI (`.github/workflows/ci.yml`) currently runs only the Flutter side on
push/PR to `main`. Adding a Python job is itself a good first PR.

## Conventions

- Cross-platform helpers in `hosts/_common.py`; OS-bound side effects
  in `hosts/<platform>.py`. **No `winreg` / `winsound` / `ctypes.windll`
  outside `hosts/windows.py`.**
- Each `PostLikeAction` is independent — a failure must not abort the
  chain (see `like_spotify/core/pipeline.py`).
- "Abstractions need two real implementations" — when you add an
  interface, also ship the second concrete impl (or wait until you
  have a second use case in hand).
- Issues drive scope; the design lives in issue bodies. Decisions live
  in commit messages and the design docs under `docs/design/`.
