const {test} = require('node:test');
const assert = require('node:assert/strict');
const calendar = require('../web/static/js/fixture_calendar.js');
const fixture = (day, status = 'NS', id = 1) => ({match_date: `${day}T18:00:00`, status, fixture_id: id});

test('opens nearest upcoming day rather than final day of season', () => {
    const fixtures = [fixture('2027-05-30'), fixture('2026-09-20'),
        fixture('2026-09-14', 'FT'), fixture('2026-09-19', 'PST')];
    assert.equal(calendar.defaultDay(fixtures, new Date('2026-09-18T12:00:00')), '2026-09-20');
});

test('completed season opens last played day, ignoring cancelled fixtures', () => {
    assert.equal(calendar.defaultDay([fixture('2025-05-25', 'FT'), fixture('2025-05-30', 'CANC')],
        new Date('2026-09-18T12:00:00')), '2025-05-25');
});

test('live matches today and local date rollover remain selectable', () => {
    assert.equal(calendar.defaultDay([fixture('2026-09-18', '2H')],
        new Date('2026-09-18T19:00:00')), '2026-09-18');
    assert.equal(calendar.dateKey(new Date(2026, 8, 19, 0, 30)), '2026-09-19');
});

test('calendar has six Monday-first weeks and validates deep links', () => {
    const days = calendar.monthDays(new Date(2026, 2, 1, 12));
    assert.equal(days.length, 42);
    assert.equal(days[0].getDay(), 1);
    assert.equal(new Set(days.map(calendar.dateKey)).size, 42);
    assert.equal(calendar.parseDay('2026-02-30'), null);
    assert.equal(calendar.parseDay('invalid'), null);
    assert.ok(calendar.parseDay('2024-02-29'));
});

test('fixtures sort by kickoff without mutating source', () => {
    const fixtures = [fixture('2026-09-20'), fixture('2026-09-19')];
    assert.equal(calendar.sortFixtures(fixtures)[0].match_date, '2026-09-19T18:00:00');
    assert.equal(fixtures[0].match_date, '2026-09-20T18:00:00');
});
