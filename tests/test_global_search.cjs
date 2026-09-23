const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    function element() {
        const classes = new Set();
        return {
            value: '', open: false, handlers: {}, innerHTML: '', textContent: '',
            classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x)},
            addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); },
            emit(type, event = {}) { for (const fn of this.handlers[type] || []) fn(event); },
            showModal() { this.open = true; }, close() { this.open = false; },
            setAttribute() {}, focus() {}, select() {}, replaceChildren() { this.innerHTML = ''; },
        };
    }
    const ids = Object.fromEntries(['button', 'overlay', 'input', 'content', 'close'].map(name => [name, element()]));
    const strong = element();
    ids.content.querySelector = () => strong;
    const timers = new Map();
    const requests = [];
    const originalInitials = () => 'existing helper';
    const context = {
        getInitials: originalInitials, AbortController, console,
        document: {
            getElementById: id => ids[id.replace('global-search-', '')],
            querySelector: () => null, body: element(), addEventListener() {},
        },
        window: {
            setTimeout(fn) { const id = {}; timers.set(id, fn); return id; },
            clearTimeout(id) { timers.delete(id); },
        },
        fetch(url, options) {
            return new Promise(resolve => requests.push({url, options, resolve}));
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/static/js/global_search.js'), 'utf8'), context);
    function flushTimers() {
        for (const [id, fn] of [...timers]) { timers.delete(id); fn(); }
    }
    return {ids, strong, timers, requests, context, originalInitials, flushTimers};
}

test('search registers input handlers without replacing page helpers', () => {
    const {ids, context, originalInitials} = setup();
    assert.equal(context.getInitials, originalInitials);
    assert.equal(ids.input.handlers.input.length, 1);
    ids.button.emit('click');
    assert.equal(ids.overlay.open, true);
    ids.close.emit('click');
    assert.equal(ids.overlay.open, false);
});

test('closing search cancels the pending debounced request', () => {
    const {ids, requests, flushTimers} = setup();
    ids.button.emit('click');
    ids.input.value = 'Leeds';
    ids.input.emit('input');
    ids.close.emit('click');
    flushTimers();
    assert.equal(requests.length, 0);
});

test('a stale response cannot replace the latest search results', async () => {
    const {ids, requests, strong, flushTimers} = setup();
    ids.button.emit('click');
    ids.input.value = 'Leeds';
    ids.input.emit('input');
    flushTimers();
    ids.input.value = 'Arsenal';
    ids.input.emit('input');
    assert.equal(requests[0].options.signal.aborted, true);
    flushTimers();
    requests[1].resolve({ok: true, json: async () => ({count: 0, query: 'Arsenal'})});
    await new Promise(resolve => setImmediate(resolve));
    requests[0].resolve({ok: true, json: async () => ({count: 0, query: 'Leeds'})});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(strong.textContent, 'Arsenal');
    ids.input.value = '';
    ids.input.emit('input');
    assert.equal(ids.content.innerHTML, '');
});
