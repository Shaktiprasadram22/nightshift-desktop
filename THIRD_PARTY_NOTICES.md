# Third-party notices

Nightshift Desktop is distributed under the GNU General Public License, version 3. See [LICENSE](LICENSE).

## Orchis / Materia

`src/nightshift_home/theme-templates/theme/` contains a locally customized installed snapshot of **Orchis Teal Dark**, by vinceliuice and contributors, based on **Materia** by nana-4 and contributors.

- Upstream: https://github.com/vinceliuice/Orchis-theme
- Base project: https://github.com/nana-4/materia-theme
- License: GNU GPL v3; the bundled `COPYING` and `LICENSES/Orchis-GPL-3.0.txt` retain the license text.
- Changes: midnight surfaces, RGB palette transforms, transparent Shell controls and panels, GTK appearance overrides, and custom edge artwork.

The precise upstream revision of the original local installation was not recorded. The complete editable CSS/XML/SVG template snapshot used by this release is included. Upstream Sass development sources and history remain available in the linked upstream project.

## Papirus

`src/nightshift_home/theme-templates/icons/` contains recolored folder/place SVGs from **Papirus**, by the Papirus Development Team and contributors. It inherits the rest of its icons from a separately installed Papirus theme.

- Upstream: https://github.com/PapirusDevelopmentTeam/papirus-icon-theme
- License: GNU GPL v3. Copies appear in the template’s `LICENSE` and `LICENSES/Papirus-GPL-3.0.txt`.
- Changes: cyan/RGB folder recoloring and an inheritance index.

## Optional dependency

**jsonc-parser 3.3.1**, Microsoft Corporation, MIT license, is installed through npm only when editor matching or development tests need it. Source: https://github.com/microsoft/node-jsonc-parser. Its package retains its own license. `node_modules` is not distributed in this repository.

## Original work and external products

Nightshift-specific Python/JavaScript, CSS overrides, clock/icon drawings, wallpaper generators, installer, tests, and documentation: copyright 2026 Nightshift Desktop contributors, distributed under GPL-3.0-only.

GTK, PyGObject, Cairo, GNOME extensions, system fonts, terminal/editor applications, and online services are separate dependencies. No proprietary application code, fonts, logos from account pages, authentication credentials, or user content is bundled. Third-party names and trademarks remain with their respective owners.
