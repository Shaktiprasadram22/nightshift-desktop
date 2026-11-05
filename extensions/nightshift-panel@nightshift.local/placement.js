// SPDX-License-Identifier: GPL-3.0-only

// Keep the original actors, including their menus and accessibility behavior.
export function moveItems(requests) {
    const placements = requests.map(({actor, target, index}) => {
        const parent = actor?.get_parent();
        if (!parent || !target?.insert_child_at_index)
            throw new Error('Nightshift: required panel controls are unavailable');
        const originalIndex = parent.get_children().indexOf(actor);
        if (originalIndex < 0)
            throw new Error('Nightshift: panel control has no original position');
        return {actor, target, index, parent, originalIndex};
    });

    const applied = [];
    try {
        for (const placement of placements) {
            applied.push(placement);
            placement.actor.get_parent().remove_child(placement.actor);
            placement.target.insert_child_at_index(placement.actor, placement.index);
        }
    } catch (error) {
        // Include an actor removed before a failed insertion, so it is not lost.
        restoreItems(applied, true);
        throw error;
    }
    return placements;
}

export function restoreItems(placements, rollback = false) {
    for (const {actor, target, parent, originalIndex} of [...placements].reverse()) {
        const current = actor.get_parent();
        // Respect another extension if it has since moved this control elsewhere.
        if (!rollback && current !== target)
            continue;
        current?.remove_child(actor);
        parent.insert_child_at_index(actor, originalIndex);
    }
}
