'use strict';
(() => {
    const $ = id => document.getElementById(id);
    const names = {matched: 'Database match', conflict: 'Disagreement', ambiguous: 'Identity / ambiguity', incomplete: 'Missing data', unsupported: 'Source review'};
    let offset = 0, total = 0, requestId = 0, checkedText = '', authorRequest = 0;
    function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
    async function api(path, body) {
        const response = await fetch('/api/trivia/bank' + path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
        if (response.status === 401) { location.assign('/login'); throw new Error('Sign in required'); }
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed');
        return data;
    }
    function error(err) { $('bank-error').textContent = err.message; $('bank-error').hidden = false; }
    function useQuestion(text) {
        $('bank-authoring').open = true; $('author-question').value = text;
        invalidateAuthor(); $('author-question').focus(); $('bank-authoring').scrollIntoView({behavior: 'smooth', block: 'start'});
    }
    function invalidateAuthor() { authorRequest++; checkedText = ''; $('author-save').disabled = true; $('author-result').textContent = ''; }
    function renderQuestion(row) {
        const q = row.content, v = row.validation, article = el('article', undefined, 'bank-question');
        const head = el('header');
        head.append(el('strong', q.id), el('span', q.section + ' / ' + q.topic), el('span', names[row.status], 'bank-status ' + row.status));
        article.append(head, el('h2', q.question));
        const details = el('details'); details.append(el('summary', 'Answer & verification'));
        const answers = el('dl', undefined, 'bank-answer');
        answers.append(el('dt', 'Reference answer'), el('dd', q.answer), el('dt', 'Database answer'), el('dd', v.answer ?? 'Not established'));
        details.append(answers, el('p', v.reason), el('p', q.check));
        if(v.publication_exclusion)details.append(el('p','Excluded from play: '+v.publication_exclusion));
        if (v.details && Object.keys(v.details).length) details.append(el('p', Object.entries(v.details).map(([key, value]) => key.replaceAll('_', ' ') + ': ' + (typeof value === 'object' ? JSON.stringify(value) : value)).join(' · ')));
        if (row.evidence_count) details.append(el('p', row.evidence_count + ' fixtures in calculation scope'));
        const sources = el('div', undefined, 'bank-sources');
        for (const source of q.sources) {
            const url = new URL(source.url);
            if (!['http:', 'https:'].includes(url.protocol)) continue;
            const link = el('a', source.key); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.title = source.title; sources.append(link);
        }
        const use = el('button', 'Use as starting question'); use.type = 'button'; use.addEventListener('click', () => useQuestion(q.question));
        details.append(sources, use); article.append(details); return article;
    }
    async function loadQuestions() {
        const own = ++requestId;
        $('bank-questions').setAttribute('aria-busy', 'true'); $('bank-error').hidden = true;
        $('bank-prev').disabled = true; $('bank-next').disabled = true;
        const params = new URLSearchParams({offset, limit: 25, search: $('bank-search').value, status: $('bank-status').value, section: $('bank-section').value, topic: $('bank-topic').value});
        try {
            const data = await api('/questions?' + params);
            if (own !== requestId) return;
            total = data.total;
            $('bank-questions').replaceChildren(...data.questions.map(renderQuestion));
            $('bank-range').textContent = total ? `${offset + 1}–${Math.min(offset + 25, total)} of ${total} questions` : 'No matching questions';
            $('bank-page-number').textContent = `${Math.floor(offset / 25) + 1} / ${Math.max(1, Math.ceil(total / 25))}`;
            $('bank-prev').disabled = offset === 0; $('bank-next').disabled = offset + 25 >= total;
        } catch (err) { if (own === requestId) error(err); }
        finally { if (own === requestId) $('bank-questions').setAttribute('aria-busy', 'false'); }
    }
    async function loadDrafts() {
        const data = await api('/authoring/drafts');
        $('author-drafts').replaceChildren(...data.drafts.map(draft => {
            const node = el('div', undefined, 'bank-draft');
            node.append(el('p', draft.question_text), el('strong', draft.calculation.answer), el('p', 'Draft · ' + draft.draft_id)); return node;
        }));
        if (!data.drafts.length) $('author-drafts').textContent = 'No saved drafts';
    }
    $('bank-filters').addEventListener('submit', event => { event.preventDefault(); offset = 0; loadQuestions(); });
    for (const id of ['bank-status', 'bank-section', 'bank-topic']) $(id).addEventListener('change', () => { offset = 0; loadQuestions(); });
    $('bank-prev').addEventListener('click', () => { offset = Math.max(0, offset - 25); loadQuestions(); });
    $('bank-next').addEventListener('click', () => { offset += 25; loadQuestions(); });
    $('author-question').addEventListener('input', invalidateAuthor);
    $('author-form').addEventListener('submit', async event => {
        event.preventDefault(); const own = ++authorRequest, question = $('author-question').value.trim();
        $('author-check').disabled = true; $('author-save').disabled = true; $('author-result').textContent = 'Checking…';
        try {
            const data = await api('/authoring/check', {question});
            if (own !== authorRequest) return;
            const c = data.calculation;
            $('author-result').textContent = `Suggested topic: ${data.topic || 'Unclassified'}\n` + (c.status === 'calculated' ? `Database answer: ${c.answer}\n${JSON.stringify(c.details)}` : `${names[c.status] || c.status}: ${c.reason}`);
            checkedText = c.status === 'calculated' ? question : ''; $('author-save').disabled = !checkedText;
            $('author-neighbors').replaceChildren(...data.neighbors.map(row => {
                const node = el('div', undefined, 'bank-neighbor'), button = el('button', 'Use this question'); button.type = 'button';
                button.addEventListener('click', () => useQuestion(row.question));
                node.append(el('small', row.id + ' · ' + row.topic + ' · ' + names[row.validation_status]), el('p', row.question), button); return node;
            }));
        } catch (err) { if (own === authorRequest) $('author-result').textContent = err.message; }
        finally { $('author-check').disabled = false; }
    });
    $('author-save').addEventListener('click', async () => {
        const question = $('author-question').value.trim(), own = authorRequest;
        if (!checkedText || checkedText !== question) return;
        $('author-save').disabled = true;
        try {
            const data = await api('/authoring/drafts', {question});
            if (own === authorRequest) { $('author-result').textContent = 'Draft saved · ' + data.draft_id + '\nDatabase answer: ' + data.calculation.answer; checkedText = ''; }
            await loadDrafts();
        } catch (err) { if (own === authorRequest) { $('author-result').textContent = err.message; $('author-save').disabled = false; } }
    });
    async function start() {
        try {
            const data = await api('/summary');
            $('bank-total').textContent = data.question_count.toLocaleString('en') + ' questions';
            for (const [key, label] of Object.entries(names)) {
                const node = el('div'); node.append(el('strong', String(data.summary[key] || 0)), el('span', label)); $('bank-counts').append(node);
            }
            $('bank-provenance').textContent = 'Reference answers: user-attested · Database audit: ' + new Date(data.created_at).toLocaleDateString('en-GB') + ' · ' + data.source_name;
            for (const [id, values] of [['bank-section', data.sections], ['bank-topic', data.topics]]) for (const value of values) { const option = el('option', value); option.value = value; $(id).append(option); }
            $('bank-model').textContent = data.model ? `${data.model.training_rows.toLocaleString('en')} examples · held-out topic accuracy ${(data.model.test_topic_accuracy * 100).toFixed(1)}%` : 'Model not trained';
            await loadQuestions(); await loadDrafts();
        } catch (err) { error(err); $('bank-questions').setAttribute('aria-busy', 'false'); }
    }
    start();
})();
