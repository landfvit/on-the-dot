const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    const elements = new Map(), requests = [];
    function element(tag = 'div') {
        return {tag, textContent: '', value: '', disabled: false, hidden: false, children: [], handlers: {},
            classList: {toggle() {}}, focus() {},
            append(...nodes) { this.children.push(...nodes); }, replaceChildren(...nodes) { this.children = nodes; },
            addEventListener(type, fn) { this.handlers[type] = fn; }, emit(type) { this.handlers[type]?.({preventDefault() {}}); }};
    }
    const document = {createElement: element, getElementById(id) {
        if (!elements.has(id)) elements.set(id, element()); return elements.get(id);
    }};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../trivia_app/static/writer.js'), 'utf8'), {
        document, location: {assign() {}}, fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); }
    });
    return {get: id => document.getElementById(id), requests};
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const reply = (req, data, status = 200) => req.resolve({ok: status === 200, status, json: async () => data});
async function ready() {
    const s = setup(); reply(s.requests[0], {available: true, examples: ['Who scored the most goals for Manchester United in 2017/18?']});
    await flush(); return s;
}
const calculation = {answer: 'Romelu Lukaku', details: {goals: 16}, evidence_fixture_ids: [1, 2]};

test('examples fill the user question without sending or rewriting it', async () => {
    const s = await ready(); s.get('writer-examples').children[0].children[0].emit('click');
    assert.match(s.get('writer-question').value, /Manchester United/);
    assert.equal(s.requests.length, 1);
    assert.equal(s.get('writer-save').disabled, true);
});

test('model interpretation needs confirmation and preserves the original input', async () => {
    const s = await ready(); s.get('writer-question').value = 'My own original question';
    s.get('writer-form').emit('submit');
    assert.deepEqual(JSON.parse(s.requests.at(-1).options.body), {question: 'My own original question'});
    reply(s.requests.at(-1), {status: 'confirm_interpretation', token: 'signed', interpretation: 'Canonical meaning', calculation: null}); await flush();
    assert.equal(s.get('writer-question').value, 'My own original question');
    assert.equal(s.get('writer-answer-section').hidden, true);
    assert.equal(s.get('writer-save').disabled, true);
    s.get('writer-confirm').emit('click');
    assert.deepEqual(JSON.parse(s.requests.at(-1).options.body), {token: 'signed'});
    reply(s.requests.at(-1), {token: 'confirmed', calculation}); await flush();
    assert.equal(s.get('writer-answer').textContent, 'Romelu Lukaku');
    assert.equal(s.get('writer-details').children[1].textContent, '16');
    assert.equal(s.get('writer-save').disabled, false);
});

test('editing invalidates an interpretation and discards in-flight answers', async () => {
    const s = await ready(); s.get('writer-question').value = 'First user question'; s.get('writer-form').emit('submit');
    const pending = s.requests.at(-1);
    s.get('writer-question').value = 'Changed question'; s.get('writer-question').emit('input');
    reply(pending, {status: 'calculated', token: 'stale', interpretation: 'Old meaning', calculation}); await flush();
    assert.equal(s.get('writer-answer').textContent, '');
    assert.equal(s.get('writer-save').disabled, true);
    s.get('writer-save').emit('click'); assert.equal(s.requests.length, 2);
});

test('exact supported question shows the DB answer without a neural confirmation', async () => {
    const s = await ready(); s.get('writer-question').value = 'Exact question'; s.get('writer-form').emit('submit');
    reply(s.requests.at(-1), {status: 'calculated', token: 'verified', interpretation: 'Exact question', calculation}); await flush();
    assert.equal(s.get('writer-confirm').hidden, true);
    assert.equal(s.get('writer-answer-section').hidden, false);
    s.get('writer-save').emit('click');
    assert.deepEqual(JSON.parse(s.requests.at(-1).options.body), {token: 'verified'});
    reply(s.requests.at(-1), {draft_id: 'draft-1'}); await flush();
    assert.equal(s.get('writer-save').disabled, true);
});

test('double submit is bounded and errors do not enable saving', async () => {
    const s = await ready(); s.get('writer-question').value = 'Unsupported question';
    s.get('writer-form').emit('submit'); s.get('writer-form').emit('submit');
    assert.equal(s.requests.length, 2);
    reply(s.requests.at(-1), {detail: 'Include an explicit season.'}, 422); await flush();
    assert.equal(s.get('writer-status').textContent, 'Include an explicit season.');
    assert.equal(s.get('writer-submit').disabled, false);
    assert.equal(s.get('writer-save').disabled, true);
});

test('question and answer content are treated as text, not markup', async () => {
    const s = await ready(); s.get('writer-form').emit('submit');
    const hostile = '<img src=x onerror=alert(1)>';
    reply(s.requests.at(-1), {status: 'calculated', token: 'safe', interpretation: hostile,
        calculation: {...calculation, answer: hostile}}); await flush();
    assert.equal(s.get('writer-meaning').textContent, hostile);
    assert.equal(s.get('writer-answer').textContent, hostile);
    assert.equal(s.get('writer-answer').innerHTML, undefined);
});

test('partial career results show coverage and never enable saving', async () => {
    const s = await ready(); s.get('writer-form').emit('submit');
    reply(s.requests.at(-1), {status: 'calculated', token: 'partial', interpretation: 'All career seasons',
        calculation: {...calculation, savable: false, coverage: {status: 'partial', message: 'Missing career coverage'}}}); await flush();
    assert.match(s.get('writer-evidence').textContent, /Incomplete/);
    assert.equal(s.get('writer-status').textContent, 'Missing career coverage');
    assert.equal(s.get('writer-save').disabled, true);
    s.get('writer-save').emit('click');
    assert.equal(s.requests.length, 2);
});

test('recognized but unavailable queries do not show a calculate button', async () => {
    const s = await ready(); s.get('writer-form').emit('submit');
    reply(s.requests.at(-1), {status: 'recognized_unavailable', token: null, interpretation: 'Career assists',
        calculation: null, message: 'Calculation not available'}); await flush();
    assert.equal(s.get('writer-meaning').textContent, 'Career assists');
    assert.equal(s.get('writer-confirm').hidden, true);
    assert.equal(s.get('writer-save').disabled, true);
    assert.equal(s.get('writer-status').textContent, 'Calculation not available');
});
