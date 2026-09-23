(function () {
    const $ = id => document.getElementById(id);
    let attempt = null, busy = false, pending = null;
    function store(id) { try { if (id) localStorage.setItem('points-attempt', id); else localStorage.removeItem('points-attempt'); } catch (_) {} }
    function stored() { try { return localStorage.getItem('points-attempt'); } catch (_) { return null; } }
    async function request(path, body) {
        const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const data = await response.json();
        if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : 'Please check your answer.'); error.status = response.status; throw error; }
        return data;
    }
    function answerLabel(answer) {
        if (answer.kind === 'entity') return answer.entity_type === 'colour' ? answer.label : `${answer.label}: ${answer.value} ${answer.unit || 'goals'}`;
        return `${answer.value}${answer.kind === 'percentage' ? '%' : ` ${answer.unit || ''}`}`;
    }
    function show() {
        $('quiz-list').hidden = true; $('quiz-resume').hidden = true; $('quiz-game').hidden = false;
        $('quiz-status').textContent = ''; $('quiz-feedback').textContent = ''; $('quiz-next').hidden = true;
        $('quiz-review').replaceChildren();
        $('quiz-progress').textContent = `${attempt.answered} / ${attempt.total} answered | ${attempt.score} correct`;
        $('quiz-answer-form').hidden = attempt.finished;
        if (attempt.finished) {
            $('quiz-question').textContent = `${attempt.score} / ${attempt.total}`;
            for (const q of attempt.review) {
                const row = document.createElement('article'); row.className = `quiz-review${q.correct ? '' : ' incorrect'}`;
                const label = document.createElement('strong'), wording = document.createElement('p'), response = document.createElement('p');
                label.textContent = q.correct ? 'Correct' : 'Incorrect'; wording.textContent = q.question_text;
                response.textContent = `Your answer: ${q.response.text ?? q.response.value}. Answer: ${answerLabel(q.answer)}`;
                row.append(label, wording, response); $('quiz-review').append(row);
            }
            return;
        }
        $('quiz-question').textContent = attempt.question.question_text;
        $('quiz-answer').type = attempt.question.answer_kind === 'entity' ? 'text' : 'number';
        $('quiz-answer').step = attempt.question.answer_kind === 'integer' ? '1' : attempt.question.answer_kind === 'decimal' ? '0.01' : '0.1';
        $('quiz-answer').value = ''; $('quiz-answer').disabled = false; $('quiz-submit').disabled = false;
    }
    async function load() {
        $('quiz-retry').hidden = true;
        try {
            const data = await request('/api/trivia/play/quizzes'); $('quiz-list').replaceChildren();
            $('quiz-status').textContent = data.quizzes.length ? '' : 'No published quizzes yet.';
            for (const quiz of data.quizzes) {
                const tile = document.createElement('article'); tile.className = 'quiz-tile';
                const count = document.createElement('small'), title = document.createElement('h2'), description = document.createElement('p'), start = document.createElement('button');
                count.textContent = `${quiz.question_count} QUESTIONS`; title.textContent = quiz.title;
                description.textContent = quiz.description; start.textContent = 'Play'; start.className = 'primary';
                start.addEventListener('click', async () => {
                    if (busy) return; busy = true; start.disabled = true;
                    try { attempt = await request(`/api/trivia/play/quizzes/${quiz.version_id}/attempts`, {}); store(attempt.attempt_id); pending = null; show(); }
                    catch (error) { $('quiz-status').textContent = error.message; }
                    finally { busy = false; start.disabled = false; }
                }); tile.append(count, title, description, start); $('quiz-list').append(tile);
            }
            $('quiz-resume').hidden = !stored();
        } catch (error) { $('quiz-status').textContent = error.message; $('quiz-retry').hidden = false; }
    }
    $('quiz-answer-form').addEventListener('submit', async event => {
        event.preventDefault(); if (busy || !attempt?.question || pending) return;
        const input = $('quiz-answer').value.trim(); if (!input) return;
        const entity = attempt.question.answer_kind === 'entity';
        if (!entity && (!Number.isFinite(Number(input)) || Math.abs(Number(input)) > 1e12)) return;
        busy = true; $('quiz-submit').disabled = true;
        try {
            const result = await request(`/api/trivia/attempts/${attempt.attempt_id}/answers/${attempt.question.position}`, entity ? {text: input} : {value: Number(input)});
            pending = result.attempt; $('quiz-answer').disabled = true;
            $('quiz-progress').textContent = `${pending.answered} / ${pending.total} answered | ${pending.score} correct`;
            $('quiz-feedback').textContent = `${result.correct ? 'Correct.' : 'Not quite.'} ${answerLabel(result.answer)}`;
            $('quiz-next').textContent = pending.finished ? 'Show results' : 'Next question'; $('quiz-next').hidden = false;
        } catch (error) { $('quiz-feedback').textContent = error.message; $('quiz-submit').disabled = false; }
        finally { busy = false; }
    });
    $('quiz-next').addEventListener('click', () => { if (!pending || busy) return; attempt = pending; pending = null; show(); $('quiz-question').focus(); });
    $('quiz-resume').addEventListener('click', async () => {
        if (busy || !stored()) return; busy = true;
        try { attempt = await request(`/api/trivia/attempts/${encodeURIComponent(stored())}`); pending = null; show(); }
        catch (error) { if ([404,410].includes(error.status)) { store(null); $('quiz-resume').hidden = true; } $('quiz-status').textContent = error.message; }
        finally { busy = false; }
    });
    $('quiz-exit').addEventListener('click', () => { if (busy) return; $('quiz-game').hidden = true; $('quiz-list').hidden = false; load(); });
    $('quiz-retry').addEventListener('click', load);
    load();
})();
