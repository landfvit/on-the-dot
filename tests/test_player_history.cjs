const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../web/static/js/player_history.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function element(tag = 'div') {
    return {tagName: tag.toUpperCase(), textContent: '', value: '', children: [], handlers: {}, attributes: {}, dataset: {},
        append(...children) { this.children.push(...children); }, prepend(child) { this.children.unshift(child); },
        replaceChildren(...children) { this.children = children; },
        addEventListener(name, fn) { this.handlers[name] = fn; },
        setAttribute(name, value) { this.attributes[name] = value; }, getAttribute(name) { return this.attributes[name]; },
        click() { this.handlers.click?.(); }, focus() { this.focused = true; },
    };
}
async function render(data, ok = true) {
    const ids = {}, get = id => ids[id] ||= element();
    const tabs = ['overview', 'seasons', 'clubs', 'transfers'].map(name => {
        const tab = element('button'); tab.dataset.playerTab = name; tab.attributes['aria-controls'] = `player-panel-${name}`; return tab;
    });
    get('player-page').dataset = {playerId: '909', season: '2024'};
    let url;
    vm.runInNewContext(script, {
        document: {getElementById: get, createElement: element, querySelectorAll: () => tabs},
        window: {addEventListener() {}}, location: {hash: '#seasons'}, history: {replaceState() {}},
        fetch: async value => { url = value; return {ok, json: async () => data}; },
    });
    await tick(); return {ids, tabs, url};
}
const club = id => ({team_id: id, team_name: `Club ${id}`, name: `Club ${id}`, logo_url: `https://example.org/${id}.png`, profile_seasons: [2024]});
const stats = {appearances: 2, goals: 1, assists: 0, yellow_cards: 0, red_cards: 0, rating: 7.25, rating_source: 'match_ratings', rated_matches: 2, warnings: []};
function data() {
    return {source: 'API-Football', duplicate_transfer_records: 0, transfer_import: {status: 'success', imported_at: '2026-09-17'},
        seasons: [{...stats, season: 2024, league_id: 39, league_name: 'Premier League', clubs: [{...club(1), ...stats}, {...club(2), ...stats}]}],
        transfers: [{date: '2024-01-01', type: 'Loan', out: club(1), in: club(2)}, {date: '2024-06-01', type: 'Return from loan', out: club(2), in: club(1)}],
        clubs: [{club: club(1), arrival_dates: ['2024-06-01'], end_date: null, entry_type: 'Return from loan', uncertain: false}]};
}

test('seasons show totals and club breakdown with rating denominators and logos', async () => {
    const {ids, url} = await render(data());
    assert.equal(url, '/api/players/909/history');
    assert.equal(ids['player-panel-overview'].hidden, true);
    assert.equal(ids['player-panel-seasons'].hidden, false);
    const rows = ids['player-seasons-body'].children;
    assert.equal(rows.length, 3);
    assert.equal(rows[0].children[2].textContent, '2');
    assert.equal(rows[0].children[7].children[0].textContent, '2 / 2 rated');
    assert.equal(rows[1].children[1].children[0].children[0].className, 'entity-team-logo-inline');
    assert.equal(rows[0].children[0].children[0].href, '/players/909?season=2024#overview');
});

test('loan filter excludes returns and restores all transfers', async () => {
    const {ids} = await render(data());
    ids['player-transfer-filter'].value = 'loan'; ids['player-transfer-filter'].handlers.change();
    assert.equal(ids['player-transfers-body'].children.length, 1);
    assert.equal(ids['player-transfers-body'].children[0].children[3].children[0].textContent, 'Loan');
    ids['player-transfer-filter'].value = 'all'; ids['player-transfer-filter'].handlers.change();
    assert.equal(ids['player-transfers-body'].children.length, 2);
});

test('keyboard tabs move selection and keep a single visible panel', async () => {
    const {ids, tabs} = await render(data());
    tabs[1].handlers.keydown({key: 'End', preventDefault() {}});
    assert.equal(tabs[3].attributes['aria-selected'], 'true');
    assert.equal(tabs[3].focused, true);
    assert.equal(ids['player-panel-transfers'].hidden, false);
    assert.equal(ids['player-panel-seasons'].hidden, true);
});

test('unknown rating remains missing and open-ended club history does not claim present', async () => {
    const fixture = data(); fixture.seasons[0].rating = null; fixture.seasons[0].rating_source = null;
    const {ids} = await render(fixture);
    assert.equal(ids['player-seasons-body'].children[0].children[7].textContent, '\u2014');
    assert.equal(ids['player-clubs-list'].children[0].children[0].children[1].textContent, 'Departure not recorded');
});

test('history API failure does not replace the player overview', async () => {
    const {ids} = await render(null, false);
    assert.equal(ids['player-history-error'].hidden, false);
    assert.equal(ids['player-history-retry'].disabled, false);
    assert.equal(ids['player-seasons-status'].textContent, 'History unavailable.');
    assert.equal(ids['player-name'], undefined);
});
