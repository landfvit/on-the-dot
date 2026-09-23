(function () {
    const $ = id => document.getElementById(id);
    let questions = [], index = 0, nextOffset = 0, answered = 0, correct = 0, busy = false, graded = false;
    async function request(url, options) {
        const response = await fetch(url, options);
        if (!response.ok) throw new Error('Trivia is temporarily unavailable. Please try again.');
        return response.json();
    }
    function show() {
        const question = questions[index];
        $('play-status').textContent = '';
        $('play-retry').hidden = true;
        $('play-question').hidden = !question;
        $('play-progress').textContent = answered ? `${correct} / ${answered} correct` : '';
        if (!question) {
            $('play-status').textContent = answered ? 'All questions completed.' : 'No published questions yet.';
            return;
        }
        graded = false;
        $('play-text').textContent = question.question_text;
        $('play-answer').value = '';
        $('play-answer').type = question.answer_kind === 'entity' ? 'text' : 'number';
        $('play-answer').step = question.answer_kind === 'integer' ? '1' : question.answer_kind === 'decimal' ? '0.01' : '0.1';
        $('play-answer').disabled = false;
        $('play-submit').disabled = false;
        $('play-next').hidden = true;
        $('play-result').textContent = '';
    }
    async function load() {
        if (busy) return;
        busy = true;
        $('play-next').disabled = true;
        $('play-retry').disabled = true;
        try {
            const data = await request(`/api/trivia/play/questions?offset=${nextOffset}`);
            questions = data.questions; index = 0; nextOffset = data.next_offset;
            show();
        } catch (error) {
            $('play-status').textContent = error.message;
            $('play-retry').hidden = false;
        } finally {
            busy = false; $('play-next').disabled = false; $('play-retry').disabled = false;
        }
    }
    $('play-form').addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || graded || !questions[index]) return;
        const input = $('play-answer').value.trim();
        if (!input) return;
        const entity = questions[index].answer_kind === 'entity';
        const value = Number(input);
        if (!entity && (!Number.isFinite(value) || Math.abs(value) > 1e12)) return;
        if (entity && input.length > 200) return;
        busy = true; $('play-submit').disabled = true;
        try {
            const data = await request(`/api/trivia/questions/${questions[index].version_id}/grade`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(entity ? {text: input} : {value}),
            });
            graded = true; answered++; correct += Number(data.correct);
            $('play-answer').disabled = true;
            const colour=data.answer.entity_type==='colour';
            $('play-result').textContent = `${data.correct ? 'Correct.' : 'Not quite.'} Answer: ${data.answer.kind === 'entity' ? colour ? data.answer.label : `${data.answer.label} (${data.answer.value} ${data.answer.unit || 'goals'})` : data.answer.value}${data.answer.kind === 'percentage' ? '%' : ''} | ${data.answer.sample_size} ${colour?'kit':'matches'}`;
            $('play-progress').textContent = `${correct} / ${answered} correct`;
            $('play-next').hidden = false;
            $('play-next').textContent = index + 1 < questions.length || nextOffset !== null ? 'Next question' : 'Finish';
        } catch (error) {
            $('play-result').textContent = error.message;
            $('play-submit').disabled = false;
        } finally { busy = false; }
    });
    $('play-next').addEventListener('click', () => {
        if (busy) return;
        if (index + 1 === questions.length && nextOffset !== null) load();
        else { index++; show(); if (questions[index]) $('play-text').focus(); }
    });
    $('play-retry').addEventListener('click', load);
    load();
})();
