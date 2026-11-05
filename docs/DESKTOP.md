# Desktop compatibility

The original setup runs on Zorin OS 18.1, GNOME Shell 46, X11, at 1920×1080. The public package has offline tests and an offscreen GTK rendering check; it has not been validated across distributions or GNOME versions.

## Which parts need which components?

| Appearance | Requirement |
| --- | --- |
| Widgets on the desktop | GTK 3, PyGObject, Cairo, GNOME X11 |
| GTK applications | Bundled Midnight-Cyan / Nightshift-RGB themes |
| Settings/libadwaita colors | Managed CSS import in `~/.config/gtk-4.0/gtk.css`; application support varies |
| Top bar, quick settings, notifications | Enabled GNOME 46-compatible User Themes extension |
| Bottom-centered dock | An installed compatible Dash to Dock extension |
| Background blur | Separately installed/enabled Blur my Shell extension |
| Folder accents | Papirus icon theme installed on the system |
| Terminal | GNOME Terminal; an existing default profile for palette settings |
| Editor colors | Existing VS Code/Cursor profile and optional npm dependency |

The installer discovers available extension schemas and skips absent components. It does not install or enable extensions. Enable only extensions you want through GNOME’s Extensions application, then select the installed `Nightshift-RGB-A` (or `B`) Shell theme. A/B slots let RGB Studio trigger a theme reload.

For subtle blur, use Blur my Shell’s preferences to configure panels/popovers; start with a light blur and adjust for your GPU and readability. There is no animation loop for the wallpaper. Transparency alone does not blur the background.

System fonts are used rather than embedded font files. Install Inter and JetBrains Mono for the intended text styling; Noto Sans/sans-serif remain fallbacks. The large clock is drawn with Cairo and requires no special font. Some secondary timer/calendar labels request Michroma and fall back if it is absent.

## Layout and controls

- Open Home settings → **Arrange desktop**. Drag the title handles or lower corner grips. Focused handles support arrow keys; Shift makes fine adjustments. Lock the layout when finished.
- The saved 1920×1080 composition scales positions on smaller displays and clamps widgets to the screen. Dense layouts may need manual adjustment. Multi-monitor arrangements have not been broadly tested.
- Click the clock for the calendar and focus timer. Use the bottom desktop controls for the launcher, layouts, project status, settings, and arrangement.
- `nightshift-home --theme`, `--manage`, `--arrange`, `--layouts`, `--launcher`, `--calendar`, and `--project` open the corresponding controls.
- Reduce motion in Home settings to suppress widget transitions. Existing Super+D and Super+Arrow bindings are retained.

## Optional top-bar layout

The included **Nightshift Panel Layout** extension places Wi-Fi, sound, and battery controls at the far left and the Activities/workspace indicator at the far right. It keeps GNOME's original controls and menus, leaves the date/time in the center, and adds no timers or keyboard bindings. Disabling it restores the original positions.

This is separate from the widget installer and currently targets **GNOME Shell 46**. From the repository checkout:

```sh
mkdir -p ~/.local/share/gnome-shell/extensions
cp -R extensions/nightshift-panel@nightshift.local ~/.local/share/gnome-shell/extensions/
```

On X11, press **Alt+F2**, enter `restart`, and press Enter to load the new extension. Then enable it:

```sh
gnome-extensions enable nightshift-panel@nightshift.local
```

If GNOME's master Extensions switch is off, review the enabled extension list before switching it on: doing so resumes all extensions still marked enabled. Other panel-layout extensions may compete for these same controls. Use one layout controller at a time.

To undo the placement:

```sh
gnome-extensions disable nightshift-panel@nightshift.local
```

Disable it before removing its directory. The main widget uninstaller does not manage this optional extension.

## Optional workspace shortcuts

An explicit helper can name three workspaces Coding, Research, and Personal, add Super+Alt+1/2/3, and bind Super+K to Quick Launch. Review these bindings against your existing shortcuts before running it. This is separate from the installer:

```sh
/usr/bin/python3 ~/.local/share/nightshift-home/setup_productivity.py apply
# Restore this helper's changes before uninstalling the app:
/usr/bin/python3 ~/.local/share/nightshift-home/setup_productivity.py restore
```

## Troubleshooting

**Widgets do not appear:** verify you are logged into an X11 session (`echo "$XDG_SESSION_TYPE"`), then start `~/.local/bin/nightshift-home` from a terminal to read the error. Wayland desktop positioning is not implemented.

**Shell stays unchanged:** confirm a compatible User Themes extension is enabled and select the generated theme; log out/in if necessary. Shell styles are version-sensitive. The installer never re-enables all user extensions.

**Terminal has default colors:** launch GNOME Terminal once to create its default profile, then Apply a preset in RGB Studio. Use the Nightshift Terminal launcher for the startup card.

**A Settings/Flatpak application ignores colors:** GTK4/libadwaita and sandboxed application styling varies. The installer does not grant filesystem access to sandboxed apps or replace system packages.

**CPU usage seems high:** distinguish individual-process CPU from the monitor’s total-across-cores percentage. Hide unused widgets, reduce motion, and check other applications. CPU/RAM sample every 2 seconds, storage every 30 seconds; AI and traffic are polled on longer intervals. Blur cost depends on the compositor/GPU. No fixed CPU usage guarantee is made.
