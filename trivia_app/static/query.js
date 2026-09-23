(function () {
    const $ = id => document.getElementById(id);
    let context = null, metadata = null, parsed = null, result = null, generation = 0, contextGeneration = 0, controller = null;
    const season = y => `${y}/${String(y + 1).slice(-2)}`;
    function status(message, error = false) {
        $('query-status').textContent = message; $('query-status').classList.toggle('error', error);
    }
    async function request(url, data, signal) {
        const response = await fetch(url, data ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data), signal} : {signal});
        const body = await response.json();
        if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map(d => d.msg).join('; ') : body.detail || 'Request failed');
        return body;
    }
    function invalidate() {
        generation++; controller?.abort(); parsed = result = null;
        $('query-run').disabled = true; $('query-parse').disabled = !context;
        $('query-result').hidden = true; $('query-interpretation').hidden = true;
        $('query-suggestions').replaceChildren(); status('');
    }
    function completions() {
        if (!context) return;
        const input = $('query-text').value, lower = input.toLowerCase().trim();
        let values = [];
        const team = context.teams.find(t => [t.team_name, ...t.aliases].some(n => lower.startsWith(n.toLowerCase() + ' ')));
        if (!team) values = context.teams.filter(t => [t.team_name, ...t.aliases].some(n => n.toLowerCase().includes(lower))).map(t => `${t.team_name} win rate last 5 seasons`);
        else if (/\b(against|vs)\s*(the\s*)?$/.test(lower)) values = ['Big 6', ...context.teams.filter(t => t.team_id !== team.team_id).map(t => t.team_name)].map(n => `${input.trim()} ${n} last 5 seasons`);
        else {
            values = Object.keys(context.metrics).map(m => `${team.team_name} ${m} last 5 seasons`).filter(v => v.toLowerCase().startsWith(lower));
            if (!/\b(last|since|between|all time)\b|\d{4}\//.test(lower)) values.push(...['last season', 'last 5 seasons', 'last 10 seasons'].map(p => `${input.trim()} ${p}`));
        }
        $('query-completions').replaceChildren(...values.slice(0, 12).map(value => { const o = document.createElement('option'); o.value = value; return o; }));
    }
    async function loadContext() {
        invalidate(); context = null; $('query-parse').disabled = true;
        const version = ++contextGeneration;
        try {
            const data = await request(`/api/query/catalogue?competition_id=${$('query-competition').value}&dataset_id=${metadata.dataset.dataset_id}`);
            if (version !== contextGeneration) return;
            context = data; $('query-parse').disabled = false; completions();
        } catch (error) { if (version === contextGeneration) status(error.message, true); }
    }
    $('query-tab').addEventListener('click', async () => {
        document.dispatchEvent(new CustomEvent('trivia-view', {detail: 'query'}));
        if (metadata) { if (!context) await loadContext(); return; }
        $('query-parse').disabled = true;
        try {
            metadata = await request('/api/trivia/metadata');
            $('query-competition').replaceChildren(...Object.entries(metadata.dataset.summary.leagues).map(([id, league]) => {
                const o = document.createElement('option'); o.value = id; o.textContent = league.name; return o;
            }));
            await loadContext();
        } catch (error) { status(error.message, true); }
    });
    $('query-competition').addEventListener('change', loadContext);
    $('query-text').addEventListener('input', () => { invalidate(); completions(); });
    $('query-minimum').addEventListener('input', invalidate);
    $('query-form').addEventListener('submit', async event => {
        event.preventDefault(); if (!context) return;
        invalidate(); const version = generation; controller = new AbortController();
        $('query-parse').disabled = true; status('Parsing...');
        try {
            const data = await request('/api/query/parse', {text: $('query-text').value, competition_id: Number($('query-competition').value),
                minimum_sample: Number($('query-minimum').value), dataset_id: context.dataset_id}, controller.signal);
            if (version !== generation) return;
            $('query-recognized').replaceChildren();
            const fields = {...data.recognized};
            if (data.ok) { fields.competition = data.competition; fields.venue ||= 'Home and away'; fields.opponents ||= 'All opponents'; }
            for (const [key, value] of Object.entries(fields)) {
                const term = document.createElement('dt'), detail = document.createElement('dd');
                term.textContent = key.replaceAll('_', ' ');
                detail.textContent = key === 'seasons' ? value.map(season).join(', ') : Array.isArray(value) ? value.join(', ') : value;
                $('query-recognized').append(term, detail);
            }
            $('query-interpretation').hidden = false;
            $('query-definition').textContent = data.definitions?.metric || '';
            $('query-period-definition').textContent = data.definitions?.period || '';
            $('query-snapshot').textContent = data.snapshot_date ? `Snapshot: ${new Date(data.snapshot_date).toLocaleString('en-GB')} | ${context.dataset_id}` : '';
            $('query-json').textContent = data.query ? JSON.stringify(data.query, null, 2) : 'No executable query';
            if (!data.ok) {
                status(data.issues.join(' '), true);
                for (const suggestion of data.suggestions) {
                    const button = document.createElement('button'); button.type = 'button';
                    button.textContent = suggestion.name;
                    button.addEventListener('click', () => {
                        if (suggestion.query_text) $('query-text').value = suggestion.query_text;
                        else {
                            status(`Use the full club name: ${suggestion.name}`, true); $('query-text').focus(); return;
                        }
                        invalidate(); completions(); $('query-text').focus();
                    });
                    $('query-suggestions').append(button);
                }
            } else { parsed = data.query; $('query-run').disabled = false; status('Recognized. Ready to calculate.'); }
        } catch (error) { if (version === generation && error.name !== 'AbortError') status(error.message, true); }
        finally { if (version === generation) $('query-parse').disabled = !context; }
    });
    $('query-run').addEventListener('click', async () => {
        if (!parsed) return;
        const version = generation; controller = new AbortController(); $('query-run').disabled = true; status('Calculating...');
        try {
            const data = await request('/api/query/evaluate', parsed, controller.signal);
            if (version !== generation) return;
            result = data;
            $('query-result-title').textContent = data.question_text;
            const team = metadata.teams.find(t => t.team_id === parsed.entity_id && t.league_id === parsed.competition_id);
            $('query-team-logo').hidden = !team?.logo_url; if (team?.logo_url) $('query-team-logo').src = team.logo_url;
            $('query-value').textContent = data.answer.value == null ? 'Unavailable' : data.answer.value.toFixed(data.answer.rounding_decimals);
            $('query-unit').textContent = data.answer.unit;
            $('query-record').replaceChildren(); $('query-record-bar').replaceChildren();
            const record = data.summary;
            for (const key of ['played', 'wins', 'draws', 'losses']) {
                const item = document.createElement('div'), label = document.createElement('span'), value = document.createElement('strong');
                label.textContent = key; value.textContent = record[key]; item.append(value, label); $('query-record').append(item);
                if (key !== 'played') { const bar = document.createElement('span'); bar.className = key; bar.style.width = `${record.played ? record[key] / record.played * 100 : 0}%`; $('query-record-bar').append(bar); }
            }
            $('query-record-bar').setAttribute('aria-label', `${record.wins} wins, ${record.draws} draws, ${record.losses} losses`);
            $('query-coverage').textContent = `${data.coverage.eligible_matches} / ${data.coverage.requested_matches} eligible matches | ${data.coverage.publishable ? 'Checks passed' : 'Publication blocked: ' + data.coverage.warnings.join(', ')} | ${record.goals_for}:${record.goals_against} goals`;
            $('query-result').hidden = false; status('Calculation complete.');
        } catch (error) { if (version === generation && error.name !== 'AbortError') status(error.message, true); }
        finally { if (version === generation) $('query-run').disabled = !parsed; }
    });
    $('query-team-logo').addEventListener('error', () => { $('query-team-logo').hidden = true; });
    $('query-to-editor').addEventListener('click', () => {
        if (result) document.dispatchEvent(new CustomEvent('trivia-query-result', {detail: result}));
    });
})();
