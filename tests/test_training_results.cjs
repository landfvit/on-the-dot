const assert = require('node:assert/strict');
const {test} = require('node:test');
const results = require('../trivia_app/static/training_results.js');
const base = {label:'total_goals',trained_labels:['total_goals','win_rate','unsupported'],
    scores_uncalibrated:{win_rate:0.1,total_goals:0.8,unsupported:0.1},seen_in_training:false};

test('readable scores remain uncalibrated suggestions, not football answers',()=>{
    const view=results.probe(base);
    assert.equal(view.heading,'Model suggests: Goals scored');
    assert.match(view.assessment,/No team, season or match result/);
    assert.equal(view.scores[0][0],'total_goals');
    assert.match(view.seen,/not used in training/);
});
test('known rule outside trained classes cannot be presented as a supported interpretation',()=>{
    const view=results.probe({...base,rule_label:'goals_per_game'});
    assert.equal(view.heading,'Not trained for this metric');
    assert.match(view.assessment,/no such class/);
});
test('disagreement and seen training phrases are explicit',()=>{
    const view=results.probe({...base,rule_label:'win_rate',seen_in_training:true});
    assert.equal(view.heading,'Rules and model disagree');
    assert.match(view.seen,/not an independent test/);
});
test('no features has no stale scores',()=>{
    const view=results.probe({label:null,trained_labels:base.trained_labels});
    assert.equal(view.heading,'No usable prediction');
    assert.deepEqual(view.scores,[]);
});
test('evaluation retains actual sample counts',()=>{
    const model={evaluation_examples:{validation:[{expected:'a',predicted:'a'},{expected:'a',predicted:'b'},{expected:'b',predicted:'b'}]}};
    assert.deepEqual(results.tally(model,'validation'),{correct:2,total:3});
    assert.deepEqual(results.tally(model,'test'),{correct:0,total:0});
});
