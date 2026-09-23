const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function render(kit) {
    function element(tag = 'div') {
        const classes = new Set();
        return {
            tag, children: [], style: {}, handlers: {}, dataset: {}, textContent: '',
            classList: {add: name => classes.add(name), contains: name => classes.has(name)},
            setAttribute() {},
            append(...children) { this.children.push(...children); },
            appendChild(child) { this.children.push(child); },
            replaceChildren(...children) { this.children = children; },
            addEventListener(type, handler) { this.handlers[type] = handler; },
        };
    }
    const page = element();
    page.dataset = {season: '2024', teamId: '39'};
    const container = element();
    const source = element('a');
    const title = element();
    let requested;
    await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/static/js/team_kits.js'), 'utf8'), {
        document: {
            getElementById: id => ({'team-page': page, 'team-kits': container, 'team-kits-source': source})[id],
            querySelector: () => title, createElement: element,
        },
        fetch: async url => {
            requested = url;
            return {ok: true, json: async () => ({kits: [kit], source_url: 'https://commons.wikimedia.org/'})};
        },
    });
    return {drawing: container.children[0].children[0], requested, title};
}

const historicalKit = {label: 'Home', layers: [{
    left: 31, top: 0, width: 38, height: 59, color: '#ff9900',
    image_url: 'https://upload.wikimedia.org/kit.png', source_url: 'https://commons.wikimedia.org/wiki/File:Kit.png',
}]};

test('historical layers use exact colors and responsive pixel geometry', async () => {
    const {drawing, requested, title} = await render(historicalKit);
    assert.equal(requested, '/api/teams/39/kits?season=2024');
    assert.equal(title.textContent, '2024/25');
    assert.equal(drawing.classList.contains('pixel'), true);
    const part = drawing.children[0];
    assert.equal(part.style.left, '31%');
    assert.equal(part.style.width, '38%');
    assert.equal(parseFloat(part.style.height), 59 / 135 * 100);
    assert.equal(part.style.backgroundColor, '#ff9900');
});

test('missing local export falls back to the same season source layers', async () => {
    const {drawing} = await render({...historicalKit, image_url: '/assets/kits/2024/39/home.svg'});
    assert.equal(drawing.children[0].src, '/assets/kits/2024/39/home.svg');
    drawing.children[0].handlers.error();
    assert.equal(drawing.children[0].children[0].src, historicalKit.layers[0].image_url);
    assert.equal(drawing.classList.contains('pixel'), true);
});

test('unavailable historical kit never becomes a guessed graphic', async () => {
    const {drawing} = await render({label: 'Third', layers: []});
    assert.equal(drawing.textContent, 'Not available');
    assert.equal(drawing.children.length, 0);
});
