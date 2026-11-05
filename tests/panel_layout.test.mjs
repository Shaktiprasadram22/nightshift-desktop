import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

// Load the dependency-free layout logic as an ES module, like GNOME Shell does.
const source = await readFile(new URL('../extensions/nightshift-panel@nightshift.local/placement.js', import.meta.url));
const {moveItems, restoreItems} = await import(`data:text/javascript;base64,${source.toString('base64')}`);

class Box {
    children = [];
    get_children() { return [...this.children]; }
    remove_child(actor) {
        assert.equal(actor.parent, this);
        this.children.splice(this.children.indexOf(actor), 1);
        actor.parent = null;
    }
    insert_child_at_index(actor, index) {
        assert.equal(actor.parent, null);
        this.children.splice(index < 0 ? this.children.length : index, 0, actor);
        actor.parent = this;
    }
}

function fixture() {
    const left = new Box(), right = new Box();
    const add = (name, box) => {
        const actor = {name, parent: null, get_parent() { return this.parent; }};
        box.insert_child_at_index(actor, -1);
        return actor;
    };
    const activities = add('workspaces', left);
    add('app menu', left);
    add('tray', right);
    const quick = add('system', right);
    const requests = [{actor: quick, target: left, index: 0},
        {actor: activities, target: right, index: -1}];
    const order = () => [left, right].map(box => box.children.map(actor => actor.name));
    return {left, right, activities, requests, order};
}

test('moves original controls and restores the order of adjacent controls', () => {
    const f = fixture();
    const before = f.order();
    const saved = moveItems(f.requests);
    assert.deepEqual(f.order(), [['system', 'app menu'], ['tray', 'workspaces']]);
    restoreItems(saved);
    assert.deepEqual(f.order(), before);
});

test('missing controls leave the entire panel unchanged', () => {
    const f = fixture(), before = f.order();
    f.requests[1].actor = null;
    assert.throws(() => moveItems(f.requests), /unavailable/);
    assert.deepEqual(f.order(), before);
});

test('failed insertion restores both controls, including the detached actor', () => {
    const f = fixture(), before = f.order();
    const insert = f.right.insert_child_at_index;
    f.right.insert_child_at_index = function (actor, index) {
        this.insert_child_at_index = insert;
        throw new Error('insertion failed');
    };
    assert.throws(() => moveItems(f.requests), /insertion failed/);
    assert.deepEqual(f.order(), before);
});

test('disable respects a later move made by another extension', () => {
    const f = fixture(), elsewhere = new Box();
    const saved = moveItems(f.requests);
    f.right.remove_child(f.activities);
    elsewhere.insert_child_at_index(f.activities, -1);
    restoreItems(saved);
    assert.deepEqual(f.order(), [['app menu'], ['tray', 'system']]);
    assert.equal(f.activities.parent, elsewhere);
});
