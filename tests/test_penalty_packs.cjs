const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
  const nodes = new Map(), requests = [], radio = {value: 'solo'};
  function element(tag = 'div') {
    let value = '';
    return {tag, children: [], handlers: {}, disabled: false, hidden: false, textContent: '',
      get value() { return value || (tag === 'select' ? this.children[0]?.children[0]?.value || '' : ''); },
      set value(v) { value = v; },
      classList: {toggle() {}}, style: {},
      append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; },
      addEventListener(type, fn) { this.handlers[type] = fn; }, emit(type) { return this.handlers[type]?.({preventDefault() {}}); },
    };
  }
  const get = id => { if (!nodes.has(id)) nodes.set(id, element(id === 'pack' ? 'select' : 'div')); return nodes.get(id); };
  const document = {getElementById: get, createElement: element,
    querySelector: selector => selector === '.penalty-page' ? element() : radio,
    querySelectorAll: () => [get('mode-solo'), get('mode-pvp')]};
  get('create-game').disabled = true; get('pack').disabled = true;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../trivia_app/static/penalties.js'), 'utf8'), {
    document, location: {href: 'http://localhost/penalties'}, URL, console, setInterval() {},
    fetch(url, options) { return new Promise(resolve => requests.push({url, options, resolve})); },
  });
  return {get, requests, radio};
}
const flush = () => new Promise(resolve => setImmediate(resolve));
function reply(request, body, status = 200) { request.resolve({ok: status === 200, status, json: async () => body}); }
const packs = [
  {id:'bank:release:GEN',label:'General',count:250,verified_count:232,language:'EN',group:'Premier League'},
  {id:'bank:release:ALL',label:'Premier League · mix',count:1950,group:'Premier League'},
  {id:'bank:release:MUN',label:'Manchester United',count:50,verified_count:44,language:'EN',group:'Teams'},
  {id:'library',label:'Published library',count:7,group:'Other packs'},
];

test('pack selection loads groups and defaults to General rather than maths', async () => {
  const s = setup(); assert.equal(s.get('create-game').disabled, true);
  reply(s.requests[0], {packs}); await flush();
  assert.equal(s.get('pack').value, packs[0].id);
  assert.equal(s.get('pack').disabled, false);
  assert.deepEqual(s.get('pack').children.map(g => g.label), ['Premier League','Teams','Other packs']);
  assert.equal(s.get('create-game').disabled, false);
  assert.equal(s.get('pack-label').textContent, 'General');
  assert.equal(s.get('create-game').textContent, 'Play solo');
  assert.equal(s.get('pack-status').textContent, '250 questions · EN');
});

test('team selection updates labels and incomplete PvP pools cannot start', async () => {
  const s = setup(); reply(s.requests[0], {packs}); await flush();
  s.get('pack').value = packs[2].id; s.get('pack').emit('change');
  assert.equal(s.get('pack-label').textContent, 'Manchester United');
  assert.equal(s.get('create-game').disabled, false);
  s.radio.value = 'pvp'; s.get('mode-pvp').emit('change');
  assert.equal(s.get('create-game').textContent, 'Create room');
  assert.match(s.get('rules-note').textContent, /First to 10 goals/);
  assert.equal(s.get('create-game').disabled, false);
  s.get('pack').value = 'library'; s.get('pack').emit('change');
  assert.equal(s.get('create-game').disabled, true);
  assert.match(s.get('pack-status').textContent, /requires 40/);
});

test('failed catalogue request does not silently start another pack', async () => {
  const s = setup(); reply(s.requests[0], {detail:'Unavailable'}, 503); await flush();
  assert.equal(s.get('create-game').disabled, true);
  assert.equal(s.get('error').textContent, 'Unavailable');
});

test('single-question packs use singular English labels', async () => {
  const s = setup(); reply(s.requests[0], {packs:[{id:'library',label:'Library',count:1}]}); await flush();
  assert.equal(s.get('pack-status').textContent, '1 question');
  assert.equal(s.get('match-label').textContent, 'Solo · 1 shot');
  assert.match(s.get('rules-note').textContent, /^Solo: 1 shot, /);
  assert.equal(s.get('pack').children[0].label, 'Other packs');
});

test('unstructured API failures have an English fallback', async () => {
  const s = setup(); reply(s.requests[0], {}, 500); await flush();
  assert.equal(s.get('error').textContent, 'Unable to process the request.');
});
