const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    const elements = new Map(), requests = [];
    function element(tag = 'div') {
        return {tag, textContent: '', value: '', disabled: false, hidden: false, open: false, children: [], attrs: {}, handlers: {},
            append(...nodes) { this.children.push(...nodes); },
            replaceChildren(...nodes) { this.children = nodes; },
            addEventListener(type, fn) { this.handlers[type] = fn; },
            emit(type) { return this.handlers[type]?.({preventDefault() {}}); },
            setAttribute(key, value) { this.attrs[key] = value; }, focus() {}, scrollIntoView() {},
        };
    }
    const document = {createElement: element, getElementById(id) {
        if (!elements.has(id)) elements.set(id, element()); return elements.get(id);
    }};
    const context = {document, URL, URLSearchParams, Date, console, location: {assign() {}},
        fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); }};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../trivia_app/static/bank.js'), 'utf8'), context);
    return {get: id => document.getElementById(id), requests};
}
const flush = () => new Promise(resolve => setImmediate(resolve));
function reply(request, body) { request.resolve({ok: true, status: 200, json: async () => body}); }
async function ready() {
    const s = setup();
    reply(s.requests[0], {question_count: 1950, summary: {matched: 1736, ambiguous: 6, incomplete: 47, unsupported: 161},
        source_name: 'bank.md', created_at: '2026-09-21', sections: ['Arsenal'], topics: ['Scoring'], model: {training_rows: 1950, test_topic_accuracy: .67}});
    await flush(); reply(s.requests[1], {total: 0, questions: []});
    await flush(); reply(s.requests[2], {drafts: []}); await flush(); return s;
}

test('bank renders counts and labels topic accuracy without claiming answer accuracy', async () => {
    const s = await ready();
    assert.equal(s.get('bank-total').textContent, '1,950 questions');
    assert.equal(s.get('bank-counts').children.length, 5);
    assert.match(s.get('bank-model').textContent, /held-out topic accuracy 67.0%/);
    assert.equal(s.get('bank-range').textContent, 'No matching questions');
    assert.equal(s.get('bank-next').disabled, true);
});

test('bank does not render source text as HTML and keeps supplied answer separate', async () => {
    const s = await ready(); s.get('bank-filters').emit('submit');
    const hostile = '<img src=x onerror=alert(1)>';
    reply(s.requests.at(-1), {total: 1, questions: [{content: {id: 'A-001', question: hostile, section: 'Arsenal', topic: 'Scoring', answer: '10', check: 'Reference note', sources: []},
        status: 'conflict', validation: {answer: '11', reason: 'Disagreement', details: {}}, evidence_count: 38}]});
    await flush();
    const article = s.get('bank-questions').children[0];
    assert.equal(article.children[1].textContent, hostile);
    const answers = article.children[2].children[1];
    assert.equal(answers.children[1].textContent, '10');
    assert.equal(answers.children[3].textContent, '11');
});

test('stale filter response cannot overwrite the latest result', async () => {
    const s = await ready(); s.get('bank-search').value = 'Arsenal'; s.get('bank-filters').emit('submit'); const old = s.requests.at(-1);
    s.get('bank-search').value = 'Chelsea'; s.get('bank-filters').emit('submit'); const current = s.requests.at(-1);
    reply(current, {total: 0, questions: []}); await flush();
    reply(old, {total: 99, questions: []}); await flush();
    assert.equal(s.get('bank-range').textContent, 'No matching questions');
});

test('editing a checked question disables saving and ignores stale model output', async () => {
    const s = await ready();
    s.get('author-question').value = 'First question'; s.get('author-form').emit('submit');
    const old = s.requests.at(-1);
    s.get('author-question').value = 'New question'; s.get('author-question').emit('input');
    reply(old, {topic: 'Scoring', calculation: {status: 'calculated', answer: '99', details: {}}, neighbors: []}); await flush();
    assert.equal(s.get('author-save').disabled, true);
    assert.equal(s.get('author-result').textContent, '');
});

test('unsupported questions cannot enable save and valid drafts send no client answer', async () => {
    const s = await ready(); s.get('author-question').value = 'Question without coverage'; s.get('author-form').emit('submit');
    reply(s.requests.at(-1), {topic: 'Scoring', calculation: {status: 'incomplete', reason: 'Missing season', answer: null}, neighbors: []}); await flush();
    assert.equal(s.get('author-save').disabled, true);
    s.get('author-form').emit('submit');
    reply(s.requests.at(-1), {topic: 'Scoring', calculation: {status: 'calculated', answer: '9', details: {}}, neighbors: []}); await flush();
    assert.equal(s.get('author-save').disabled, false);
    s.get('author-save').emit('click');
    assert.deepEqual(JSON.parse(s.requests.at(-1).options.body), {question: 'Question without coverage'});
    assert.equal(s.get('author-save').disabled, true);
});
