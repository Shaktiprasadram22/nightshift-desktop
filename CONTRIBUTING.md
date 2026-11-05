# Contributing

Start with a focused issue or pull request describing the problem, affected desktop version, and expected behavior. Screenshots should use demo data. Do not attach your real configuration directory, journal, accounts, mail, notes, or session database.

## Source map

- `src/nightshift_home/home.py`: native GTK application and desktop windows.
- `style.css`, `*-panel.py` / `*_panel.py`, `line_clock.py`, `shortcut_glyphs.py`: widgets and drawing.
- `theme_palette.py`, `theme_apply.py`, `theme_studio.py`: coordinated palette preview, validation, transactional Apply/Undo.
- `theme-templates/`, `theme-shell-overrides.css`: editable GTK/Shell/folder assets.
- `aurora_art.py`, `terminal/rgb_art.py`: original static wallpaper/art generators.
- `terminal/`: GNOME Terminal and Settings launchers and shell startup card.
- `*_data.py`, `google_*.py`, `cloudflare_*.py`, `personal_store.py`: integration adapters and local stores.
- `install.py`: per-user installation and restore journal.
- `tests/`, `tools/test.py`: offline regression and installer tests.
- `tools/render_demo.py`: synthetic-data GTK preview and allocation check.

## Validate changes

```sh
npm ci --ignore-scripts --prefix src/nightshift_home
/usr/bin/python3 tools/test.py
dbus-run-session -- /usr/bin/python3 tools/verify_learning_ui.py
dbus-run-session -- /usr/bin/python3 tools/render_demo.py
```

The renderer needs an X display; CI uses Xvfb. It uses offscreen windows and its own temporary profile. Some GTK versions log offscreen-window origin warnings; a successful render still checks widget allocation bounds. Review the resulting image for clipping, overlap, contrast, and readability.

Use `NIGHTSHIFT_HOME` for disposable application data and `GSETTINGS_BACKEND=memory` for settings tests. Do not point tests at your live configuration or repurpose `HOME`. Use fake backends for desktop transactions. Integration tests must not contact real accounts.

Keep keyboard accessibility, reduced motion, cached/error states, and transparent surfaces readable. Preserve unrelated application settings and user data. New dependencies require a clear purpose, pinned version where appropriate, and compatible license.

Contributions are accepted under GPL-3.0-only; preserve upstream notices when editing derived theme/icon files.
