// SPDX-License-Identifier: GPL-3.0-only
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
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

        this._activities = Main.panel.statusArea.activities;
        this._hoverSignals = [
            this._activities.connect('notify::hover', () => this._onHoverChanged()),
            this._activities.connect('captured-event', (_actor, event) => {
                if ([Clutter.EventType.BUTTON_PRESS, Clutter.EventType.TOUCH_BEGIN,
                    Clutter.EventType.KEY_PRESS].includes(event.type()))
                    this._cancelHover();
                return Clutter.EVENT_PROPAGATE;
            }),
        ];
    }

    _onHoverChanged() {
        this._cancelHover();
        if (!this._canOpenOverview())
            return;

        // A single dwell delay avoids opening during a quick pointer pass.
        this._hoverTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 180, () => {
            this._hoverTimeout = 0;
            if (this._canOpenOverview())
                Main.overview.show();
            return GLib.SOURCE_REMOVE;
        });
    }

    _canOpenOverview() {
        return this._activities?.hover &&
            Main.actionMode === Shell.ActionMode.NORMAL &&
            !Main.overview.visible && Main.overview.shouldToggleByCornerOrButton();
    }

    _cancelHover() {
        if (this._hoverTimeout) {
            GLib.source_remove(this._hoverTimeout);
            this._hoverTimeout = 0;
        }
    }

    disable() {
        this._cancelHover();
        for (const id of this._hoverSignals ?? [])
            this._activities.disconnect(id);
        this._hoverSignals = null;
        this._activities = null;
        restoreItems(this._placements ?? []);
        this._placements = null;
    }
}
