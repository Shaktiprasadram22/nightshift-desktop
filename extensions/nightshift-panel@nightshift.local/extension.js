// SPDX-License-Identifier: GPL-3.0-only
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {moveItems, restoreItems} from './placement.js';

export default class NightshiftPanelLayout extends Extension {
    enable() {
        if (this._placements)
            return;

        this._placements = moveItems([
            {actor: Main.panel.statusArea.quickSettings?.container,
                target: Main.panel._leftBox, index: 0},
            {actor: Main.panel.statusArea.activities?.container,
                target: Main.panel._rightBox, index: -1},
        ]);
    }

    disable() {
        restoreItems(this._placements ?? []);
        this._placements = null;
    }
}
