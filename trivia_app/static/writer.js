'use strict';
(() => {
    const $ = id => document.getElementById(id);
    if (!$('writer-form')) return;
    let revision = 0, token = null, busy = false, savable = false;
    function status(text, error = false) { $('writer-status').textContent = text; $('writer-status').classList.toggle('error', error); }
    function node(tag, text) { const e = document.createElement(tag); e.textContent = text; return e; }
    async function api(path, body) {
        const response = await fetch('/api/trivia/writer' + path, body === undefined ? {} : {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        if (response.status === 401) { location.assign('/login'); throw new Error('Sign in to Studio.'); }
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the question and try again.');
        return data;
    }
    function invalidate() {
        revision++; token = null; savable = false;
        $('writer-interpretation').hidden = true; $('writer-answer-section').hidden = true;
        $('writer-confirm').hidden = true; $('writer-save').disabled = true;
        $('writer-answer').textContent = ''; $('writer-details').replaceChildren(); status('');
    }
    function answer(data) {
        token = data.token;
        const c = data.calculation;
        savable = c.savable !== false && c.coverage?.status !== 'partial';
        $('writer-answer').textContent = c.answer;
        $('writer-details').replaceChildren();
        for (const [key, value] of Object.entries(c.details || {})) {
            if (key === 'player_id') continue;
            const labels = {scorer_matches: 'Matches checked', goals: 'Goals', selected_matches: 'Qualifying matches', numerator: 'Numerator', denominator: 'Denominator'};
            $('writer-details').append(node('dt', labels[key] || key.replaceAll('_', ' ')), node('dd', typeof value === 'object' ? JSON.stringify(value) : String(value)));
        }
        if (c.breakdown?.length) {
            const table = node('table', '');
            const header = node('tr', '');
            for (const label of ['Season', 'Club', 'Recorded goals', 'Quality-checked', 'Provider total']) header.append(node('th', label));
            table.append(header);
            for (const row of c.breakdown) {
                const tr = node('tr', '');
                for (const value of [row.season, row.team || row.team_id, row.recorded_goals, row.quality_checked_goals, row.provider_season_goals ?? 'Unavailable']) tr.append(node('td', String(value)));
                table.append(tr);
            }
            $('writer-details').append(node('dt', 'Season breakdown'));
            const dd = node('dd', ''); dd.append(table); $('writer-details').append(dd);
        }
        $('writer-evidence').textContent = `${c.evidence_fixture_ids.length} fixtures in calculation scope | ${savable ? 'Database-verified' : 'Incomplete career verification'}`;
        $('writer-answer-section').hidden = false; $('writer-confirm').hidden = true;
        $('writer-save').disabled = !savable; status(c.coverage?.message || 'Answer calculated from the database.');
    }
    async function action(label, operation) {
        if (busy) return;
        busy = true; const own = revision;
        $('writer-submit').disabled = true; $('writer-confirm').disabled = true; $('writer-save').disabled = true;
        status(label);
        try { await operation(own); }
        catch (error) { if (own === revision) status(error.message, true); }
        finally {
            busy = false; $('writer-submit').disabled = false; $('writer-confirm').disabled = false;
            if (own === revision && !$('writer-answer-section').hidden && token && savable) $('writer-save').disabled = false;
        }
    }
    $('writer-question').addEventListener('input', invalidate);
    $('writer-form').addEventListener('submit', event => {
        event.preventDefault(); if (busy) return;
        invalidate();
        $('writer-examples-panel').open = false;
        const question = $('writer-question').value.trim();
        action('Recognizing the question...', async own => {
            const data = await api('/interpret', {question});
            if (own !== revision) return;
            token = data.token; $('writer-meaning').textContent = data.interpretation;
            $('writer-interpretation').hidden = false;
            if (data.status === 'calculated') answer(data);
            else if (data.status === 'needs_scope' || data.status === 'recognized_unavailable') status(data.message);
            else { $('writer-confirm').hidden = false; status('Model interpretation awaiting your confirmation.'); }
        });
    });
    $('writer-confirm').addEventListener('click', () => {
        if (!token) return;
        const current = token;
        action('Calculating from match data...', async own => {
            const data = await api('/answer', {token: current});
            if (own === revision) answer(data);
        });
    });
    $('writer-save').addEventListener('click', () => {
        if (!token || !savable || $('writer-answer-section').hidden) return;
        const current = token;
        action('Saving draft...', async own => {
            const data = await api('/drafts', {token: current});
            if (own !== revision) return;
            token = null; status(`Draft saved: ${data.draft_id}`);
        });
    });
    api('/metadata').then(data => {
        $('writer-model').textContent = data.recognition_available ? 'Premier League | Trained question recognition + database' : data.available ? 'Premier League | Local model + database verification' : 'Premier League | Exact questions only';
        for (const text of data.examples) {
            const li = node('li', ''), button = node('button', text); button.type = 'button';
            button.addEventListener('click', () => { $('writer-question').value = text; invalidate(); $('writer-question').focus(); });
            li.append(button); $('writer-examples').append(li);
        }
    }).catch(error => { $('writer-model').textContent = 'Unavailable'; status(error.message, true); });
})();
