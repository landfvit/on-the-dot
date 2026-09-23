const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../web/static/js/trivia_play.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function game(responses) {
    const ids = {}, calls = [];
    const document = {getElementById(id) {
        return ids[id] ||= {hidden: false, disabled: false, value: '', textContent: '', handlers: {},
            focus() {}, addEventListener(name, handler) { this.handlers[name] = handler; }};
    }};
    vm.runInNewContext(script, {document, fetch: async (url, options) => {
        calls.push({url, options}); const response = responses.shift();
        if (response instanceof Error) throw response;
        return {ok: response.ok ?? true, json: async () => response};
    }});
    await tick();
    return {ids, calls};
}

const question = {version_id: 'test-version', question_text: 'How many wins?', answer_kind: 'integer'};

test('empty public library does not create demo questions or expose editor', async () => {
    const {ids, calls} = await game([{questions: [], next_offset: null}]);
    assert.equal(ids['play-status'].textContent, 'No published questions yet.');
    assert.equal(ids['play-question'].hidden, true);
    assert.equal(calls[0].url, '/api/trivia/play/questions?offset=0');
});

test('answers are fetched only after submission and cannot be scored twice', async () => {
    const {ids, calls} = await game([{questions: [question], next_offset: null},
        {correct: true, answer: {value: 11, kind: 'integer', sample_size: 38}}]);
    assert.equal(ids['play-result'].textContent, '');
    assert.equal(ids['play-answer'].step, '1');
    ids['play-answer'].value = '11';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.equal(calls.length, 2);
    assert.equal(calls[1].url, '/api/trivia/questions/test-version/grade');
    assert.deepEqual(JSON.parse(calls[1].options.body), {value: 11});
    assert.match(ids['play-result'].textContent, /Correct. Answer: 11/);
    assert.equal(ids['play-answer'].disabled, true);
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.equal(calls.length, 2);
    ids['play-next'].handlers.click();
    assert.equal(ids['play-status'].textContent, 'All questions completed.');
});

test('failed grading keeps answer editable and retryable', async () => {
    const {ids} = await game([{questions: [question], next_offset: null}, {ok: false}]);
    ids['play-answer'].value = '11';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.equal(ids['play-submit'].disabled, false);
    assert.equal(ids['play-answer'].disabled, false);
    assert.equal(ids['play-next'].hidden, true);
});

test('load failure offers a retry', async () => {
    const {ids, calls} = await game([{ok: false}, {questions: [question], next_offset: null}]);
    assert.equal(ids['play-retry'].hidden, false);
    await ids['play-retry'].handlers.click();
    assert.equal(calls.length, 2);
    assert.equal(ids['play-retry'].hidden, true);
    assert.equal(ids['play-text'].textContent, question.question_text);
});

test('entity questions submit a name and reveal the winning label only after grading', async () => {
    const {ids, calls} = await game([{questions: [{...question, answer_kind: 'entity'}], next_offset: null},
        {correct: true, answer: {kind: 'entity', label: 'M. Salah', value: 12, sample_size: 380}}]);
    assert.equal(ids['play-answer'].type, 'text');
    assert.equal(ids['play-result'].textContent, '');
    ids['play-answer'].value = '  Mohamed Salah  ';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.deepEqual(JSON.parse(calls[1].options.body), {text: 'Mohamed Salah'});
    assert.match(ids['play-result'].textContent, /Answer: M\. Salah/);
});

test('blank answers do not turn into zero or get submitted', async () => {
    const {ids, calls} = await game([{questions: [question], next_offset: null}]);
    ids['play-answer'].value = '  ';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.equal(calls.length, 1);
});

test('kit colours grade as text without fake goals or match counts', async () => {
    const {ids,calls}=await game([{questions:[{...question,answer_kind:'entity'}],next_offset:null},
        {correct:true,answer:{kind:'entity',entity_type:'colour',label:'White',value:null,unit:'colour',sample_size:1}}]);
    ids['play-answer'].value='bila';
    await ids['play-form'].handlers.submit({preventDefault(){}});
    assert.deepEqual(JSON.parse(calls[1].options.body),{text:'bila'});
    assert.equal(ids['play-result'].textContent,'Correct. Answer: White | 1 kit');
});

test('decimal questions allow hundredths and submit the precise answer', async () => {
    const {ids, calls} = await game([{questions: [{...question, answer_kind: 'decimal'}], next_offset: null},
        {correct: true, answer: {kind: 'decimal', value: 1.84, sample_size: 19}}]);
    assert.equal(ids['play-answer'].step, '0.01');
    ids['play-answer'].value = '1.84';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    assert.deepEqual(JSON.parse(calls[1].options.body), {value: 1.84});
    assert.match(ids['play-result'].textContent, /Correct. Answer: 1.84/);
});

test('pagination keeps score and loads the next batch only when needed', async () => {
    const {ids, calls} = await game([{questions: [question], next_offset: 20},
        {correct: false, answer: {value: 11, kind: 'integer', sample_size: 38}},
        {questions: [{...question, version_id: 'next', answer_kind: 'percentage'}], next_offset: null}]);
    ids['play-answer'].value = '5';
    await ids['play-form'].handlers.submit({preventDefault() {}});
    ids['play-next'].handlers.click(); await tick();
    assert.equal(calls[2].url, '/api/trivia/play/questions?offset=20');
    assert.equal(ids['play-progress'].textContent, '0 / 1 correct');
    assert.equal(ids['play-answer'].step, '0.1');
});
