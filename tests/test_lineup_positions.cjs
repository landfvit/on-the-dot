const {test} = require('node:test');
const assert = require('node:assert/strict');
const {formationRows} = require('../web/static/js/lineup_positions.js');

test('provider positions take priority and render attack to goalkeeper', () => {
    const players = [{player_id:1, grid:'1:1'}, {player_id:2, grid:'2:2'},
        {player_id:3, grid:'2:1'}, {player_id:4, grid:'3:1'}];
    const result = formationRows(players, '4-4-2');
    assert.equal(result.estimated, false);
    assert.deepEqual(result.rows.map(row=>row.map(p=>p.player_id)), [[4],[3,2],[1]]);
});
test('fallback preserves every player and marks inferred positions', () => {
    const players = Array.from({length:11}, (_,i)=>({player_id:i,position:i===0?'G':'M'}));
    const result = formationRows(players, '4-2-3-1');
    assert.equal(result.estimated, true);
    assert.deepEqual(result.rows.map(row=>row.length), [1,3,2,4,1]);
    assert.equal(new Set(result.rows.flat().map(p=>p.player_id)).size,11);
});
test('incomplete or inconsistent data never invents missing players', () => {
    assert.equal(formationRows([], '4-4-2'), null);
    assert.equal(formationRows([{grid:'1:1'}, {grid:'1:1'}], null), null);
    assert.equal(formationRows([{grid:'99:99'}], null), null);
});
