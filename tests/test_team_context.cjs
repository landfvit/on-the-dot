const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function render(data, ok = true) {
    function element(tag = 'div') {
        return {tag, children: [], handlers: {}, textContent: '', dataset: {},
            setAttribute() {}, append(...children) { this.children.push(...children); },
            appendChild(child) { this.children.push(child); },
            replaceChildren(...children) { this.children = children; },
            addEventListener(type, handler) { this.handlers[type] = handler; },
        };
    }
    const ids = Object.fromEntries(['team-page', 'team-stadium', 'team-capacity', 'team-coaches'].map(id => [id, element()]));
    ids['team-page'].dataset = {teamId: '33', season: '2024'};
    let url;
    await vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/static/js/team_context.js'), 'utf8'), {
        document: {getElementById: id => ids[id], createElement: element},
        fetch: async value => { url = value; return {ok, json: async () => data}; },
    });
    return {ids, url};
}

test('team context renders stadium, capacity and season coaches without preview links', async () => {
    const {ids, url} = await render({venue: {venue_name: 'Old Trafford', capacity: 76212}, coach_source: 'lineups',
        coaches: [{coach_name: 'Ruben Amorim', first_name: 'Ruben Filipe', last_name: 'Marques Diogo Amorim',
            nationality: 'Portugal', photo_url: 'coach.png', matches: 27, last_match: '2025-05-25'}]});
    assert.equal(url, '/api/teams/33/context?season=2024');
    assert.equal(ids['team-stadium'].textContent, 'Old Trafford');
    assert.equal(ids['team-capacity'].textContent, '76,212');
    const coach = ids['team-coaches'].children[0];
    assert.equal(coach.tag, 'article');
    assert.equal(coach.children[1].children[1].textContent, 'Ruben Amorim');
    const portrait = coach.children[0];
    portrait.children[0].handlers.error();
    assert.equal(portrait.textContent, 'RA');
});

test('missing metadata is explicitly unavailable, never zero or another season', async () => {
    const {ids} = await render({venue: null, coaches: [], coach_source: 'careers'});
    assert.equal(ids['team-stadium'].textContent, 'Not available');
    assert.equal(ids['team-capacity'].textContent, 'Not available');
    assert.equal(ids['team-coaches'].textContent, 'No coach records available for this season.');
});

test('context failure stays local to the new information sections', async () => {
    const {ids} = await render(null, false);
    assert.equal(ids['team-coaches'].textContent, 'Could not load coaching staff.');
    assert.equal(ids['team-stadium'].textContent, 'Not available');
});
