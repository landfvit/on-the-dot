(function () {
    const $ = id => document.getElementById(id);
    let available = [], selected = [], quizId = null;
    function status(message) { $('trivia-status').textContent = message; }
    async function request(url, body) {
        const response = await fetch(url, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the quiz definition.');
        return data;
    }
    function renderChoices() {
        $('quiz-question-options').replaceChildren();
        if (!available.length) $('quiz-question-options').textContent = 'No verified, published questions yet.';
        for (const q of available) {
            const label = document.createElement('label'), check = document.createElement('input'), span = document.createElement('span');
            check.type = 'checkbox'; check.checked = selected.includes(q.version_id); span.textContent = q.question_text;
            check.addEventListener('change', () => {
                if (check.checked) selected.push(q.version_id); else selected = selected.filter(id => id !== q.version_id);
                renderOrder();
            });
            label.append(check, span); $('quiz-question-options').append(label);
        }
    }
    function renderOrder() {
        $('quiz-order').replaceChildren();
        for (const [index, id] of selected.entries()) {
            const li = document.createElement('li'), span = document.createElement('span'), select = document.createElement('select');
            span.textContent = available.find(q => q.version_id === id)?.question_text || id;
            select.setAttribute('aria-label', `Position for question ${index + 1}`);
            select.style.width = '80px';
            for (let i = 0; i < selected.length; i++) { const option = document.createElement('option'); option.value = i; option.textContent = i + 1; select.append(option); }
            select.value = index;
            select.addEventListener('change', () => { selected.splice(index, 1); selected.splice(Number(select.value), 0, id); renderOrder(); });
            const controls = document.createElement('span'); controls.className = 'quiz-order-controls'; controls.append(select);
            li.append(span, controls); $('quiz-order').append(li);
        }
        $('save-quiz').disabled = !selected.length;
    }
    async function load() {
        document.dispatchEvent(new CustomEvent('trivia-view', {detail: 'quizzes'}));
        try {
            const questions = await request('/api/trivia/questions?published_only=true'); available = questions.questions;
            selected = selected.filter(id => available.some(q => q.version_id === id));
            renderChoices(); renderOrder();
            const quizzes = await request('/api/trivia/quizzes'); $('quiz-library').replaceChildren();
            for (const quiz of quizzes.quizzes) {
                const row = document.createElement('article'); row.className = 'trivia-library-row';
                const content = document.createElement('div'), title = document.createElement('p'), detail = document.createElement('small');
                title.textContent = quiz.title; detail.textContent = `${quiz.state} | revision ${quiz.revision} | ${quiz.question_count} questions`;
                content.append(title, detail); row.append(content);
                const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = 'New revision';
                edit.addEventListener('click', async () => {
                    try {
                        const full = await request(`/api/trivia/quizzes/${quiz.version_id}`);
                        for (const q of full.questions) if (!available.some(a => a.version_id === q.version_id)) available.push(q);
                        quizId = full.quiz_id; selected = full.questions.map(q => q.version_id);
                        $('quiz-title').value = full.title; $('quiz-description').value = full.description;
                        renderChoices(); renderOrder(); $('quiz-title').focus(); status(`Editing a new revision of ${full.title}`);
                    } catch (error) { status(error.message); }
                }); row.append(edit);
                if (quiz.state === 'draft') {
                    const publish = document.createElement('button'); publish.type = 'button'; publish.textContent = 'Publish';
                    publish.addEventListener('click', async () => { publish.disabled = true;
                        try { await request(`/api/trivia/quizzes/${quiz.version_id}/publish`, {}); await load(); status('Quiz published.'); }
                        catch (error) { status(error.message); publish.disabled = false; }
                    }); row.append(publish);
                }
                $('quiz-library').append(row);
            }
        } catch (error) { status(error.message); }
    }
    $('quiz-builder').addEventListener('submit', async event => {
        event.preventDefault(); $('save-quiz').disabled = true;
        try {
            await request('/api/trivia/quizzes', {quiz_id: quizId, title: $('quiz-title').value,
                description: $('quiz-description').value, question_versions: selected});
            quizId = null; selected = []; $('quiz-builder').reset(); await load(); status('Quiz draft saved.');
        } catch (error) { status(error.message); $('save-quiz').disabled = false; }
    });
    $('quizzes-tab').addEventListener('click', load); $('refresh-quizzes').addEventListener('click', load);
})();
