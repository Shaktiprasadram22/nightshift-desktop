# Widget appearance

The separate name widget and YouTube Music mark follow Nightshift’s existing transparent midnight/RGB appearance on the native GTK desktop. The clock keeps its personalized caption.

## Separate name widget

1. Open **Home settings → Display name**, enter up to 24 characters, and choose **Save**. This updates both the clock caption and the separate name. An empty setting displays “Your name” in the separate widget.
2. Enable **Separate name widget** in Home settings. It is optional and off by default (`show_name: false`).
3. Click the name to open **Arrange desktop** with **Display name** selected. Drag its header to move it or its lower-right corner to resize it. The editor also provides **Left**, **Top**, **Width**, and **Height** fields. Focused handles accept arrow keys in 10-pixel steps, or 1-pixel steps with Shift. Choose **Done · lock layout** when finished.

Its position and size save automatically under the `name` entry in `~/.config/nightshift-home/layout.json`, independently of the clock. The preferred initial size is 360 × 96 pixels; available space can reduce this to the 160 × 72 minimum. The shared layout controls preserve Super+D and Super+Arrow shortcuts. Settings, placement, and controls are implemented in [home.py](../src/nightshift_home/home.py), [data.py](../src/nightshift_home/data.py), and [layout.py](../src/nightshift_home/layout.py).

The outlined lettering scales with the widget and ellipsizes long text instead of shrinking indefinitely. The tooltip retains the full configured name. It uses the existing Michroma, Inter, and Noto Sans font choices, takes its color from the active palette on repaint, and adds no animation or polling timer. The background remains transparent through hover and activation; keyboard focus has a visible outline. See [name_widget.py](../src/nightshift_home/name_widget.py) and [style.css](../src/nightshift_home/style.css).

## YouTube Music

The player header uses `ShortcutGlyph('music', 24)`, the same native renderer used by desktop shortcuts. Its circle and play triangle are strokes with transparent interiors and inherit the surrounding GTK theme color. See [music_panel.py](../src/nightshift_home/music_panel.py) and [shortcut_glyphs.py](../src/nightshift_home/shortcut_glyphs.py).
