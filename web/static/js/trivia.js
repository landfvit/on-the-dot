(function () {
    const $ = id => document.getElementById(id);
    const state = {metadata: null, result: null, saved: null, questionId: null, page: 0, generation: 0, controller: null, entityId: null, queryVersion: null, customOpponents: null, contextId:null};
    const reasons = {
        unfinished_or_invalid_result: 'Unfinished or invalid result', not_yet_played: 'Not yet played',
        fulltime_score_conflict: 'Conflicting final scores', missing_event_feed: 'Missing event feed',
        unresolved_var_review: 'Unresolved VAR review', unknown_goal_type: 'Unknown goal type',
        invalid_goal_time: 'Invalid goal timestamp', unknown_scoring_team: 'Unknown scoring team',
        ambiguous_duplicate_goal: 'Ambiguous duplicate goal', goal_total_mismatch: 'Goals do not match final score',
        missing_halftime_score: 'Missing half-time score', halftime_score_mismatch: 'Half-time score mismatch',
        missing_checkpoint: 'Missing checkpoint',
        invalid_goal_timeline: 'Unverified goal timeline', missing_scorer_identity: 'Unknown scorer',
        scorer_team_conflict: 'Scorer team conflict', missing_scorer_snapshot: 'Player snapshot unavailable',
        unverified_scorer_role: 'Scorer role not verified',
    };
    function status(message, error = false) {
        $('trivia-status').textContent = message;
        $('trivia-status').classList.toggle('error', error);
    }
    async function request(url, options = {}) {
        const response = await fetch(url, options);
        const data = await response.json();
        if (!response.ok) {
            const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.detail;
            throw new Error(detail || 'Request failed');
        }
        return data;
    }
    function post(url, data, signal) {
        return request(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data), signal});
    }
    function option(value, text) {
        const node = document.createElement('option'); node.value = value; node.textContent = text; return node;
    }
    function seasonLabel(season) { return `${season}/${String(season + 1).slice(-2)}`; }
    function teamBadge() {
        const team = $('template').value === 'most_comeback_wins' ? null : state.metadata?.teams.find(team => team.team_id === Number($('team').value) && team.league_id === Number($('league').value));
        $('selected-team').textContent = team?.team_name || 'Question preview';
        const image = $('selected-team-logo');
        image.hidden = !team?.logo_url;
        if (team?.logo_url) image.src = team.logo_url;
    }
    $('selected-team-logo').addEventListener('error', () => { $('selected-team-logo').hidden = true; });
    function periodControls() {
        const mode = $('period-mode').value;
        for (const name of ['seasons', 'season_range', 'dates']) {
            $(`period-${name}`).hidden = mode !== name;
            $(`period-${name}`).disabled = mode !== name;
        }
    }
    function conditions() {
        const enabled = $('template').value === 'conditional_win_rate';
        $('condition-fields').hidden = !enabled;
        $('condition-fields').disabled = !enabled;
        const stoppage = [45, 90].includes(Number($('minute').value));
        $('extra').disabled = !stoppage;
        if (!stoppage) $('extra').value = '0';
        const template = $('template').value;
        const kit = template === 'kit_colour';
        $('kit-fields').hidden=!kit; $('kit-fields').disabled=!kit;
        $('venue').disabled=kit; $('minimum-sample').disabled=kit;
        $('venue').parentElement.hidden=kit;$('minimum-sample').parentElement.hidden=kit;
        const supportsOpponents = !['player_goals', 'top_scorer', 'comeback_wins', 'most_comeback_wins','kit_colour'].includes(template);
        $('weather-fields').hidden=!supportsOpponents; $('weather-fields').disabled=!supportsOpponents;
        const weather=supportsOpponents && !!$('weather-metric').value;
        $('weather-threshold').hidden=!weather; $('weather-value').disabled=!weather; $('weather-operator').disabled=!weather;
        $('weather-value').required=weather;
        $('weather-value').min=$('weather-metric').value==='precipitation_mm'?'0':'-100';
        $('weather-value').max=$('weather-metric').value==='temperature_c'?'60':'1000';
        const context=state.metadata?.context, savedContext=state.contextId&&state.contextId!==context?.context_id;
        $('context-coverage').textContent=kit||weather ? savedContext ? `Saved context snapshot ${state.contextId.slice(0,8)}` : context ? kit ?
            `Context ${context.context_id.slice(0,8)} | ${context.summary.kit_statuses.available||0} classified kits | ${context.summary.kit_statuses.multicolour||0} multicolour | ${context.summary.kit_statuses.missing_pixels||0} missing artwork` :
            `ERA5 coverage: ${Object.entries(context.summary.weather_seasons).map(([s,n])=>`${seasonLabel(Number(s))}: ${n} matches`).join(' | ')||'No samples'}` : 'Context snapshot unavailable' : '';
        $('opponent-field').hidden = !supportsOpponents; $('opponent').disabled = !supportsOpponents;
        const scorer = ['player_goals', 'top_scorer'].includes(template);
        $('name-policy-field').hidden = template !== 'top_scorer'; $('name-policy').disabled = template !== 'top_scorer';
        $('goal-fields').hidden = !scorer; $('goal-fields').disabled = !scorer;
        const player = template === 'player_goals';
        $('player-field').hidden = !player; $('player').disabled = !player;
        $('player').required = player;
        $('team').required = !scorer && template !== 'most_comeback_wins';
        $('team').disabled = !$('league').value || template === 'most_comeback_wins';
        const emptyTeam = $('team').querySelector('option[value=""]');
        if (emptyTeam) emptyTeam.textContent = $('team').required ? 'Select team' : 'All teams';
        const goalStoppage = $('goal-minute').value !== '' && [45, 90].includes(Number($('goal-minute').value));
        $('goal-extra').disabled = !goalStoppage;
        if (!goalStoppage) $('goal-extra').value = '0';
    }
    function populateLeague() {
        const league = Number($('league').value);
        const teams = state.metadata.teams.filter(team => team.league_id === league);
        $('team').replaceChildren(option('', 'Select team'), ...teams.map(team => option(team.team_id, team.team_name)));
        $('team').disabled = !teams.length;
        const groups = (state.metadata.opponent_groups || []).filter(g => g.league_id === league);
        $('opponent').replaceChildren(option('', 'All opponents'),
            ...groups.map(g => option(`group:${g.group_key}:${g.version}`, `${g.label} v${g.version} (excluding own team)`)),
            ...teams.map(t => option(`team:${t.team_id}`, t.team_name)));
        const players = (state.metadata.players || []).filter(player => player.league_id === league);
        $('player').replaceChildren(option('', 'Select player'), ...players.map(player => option(player.player_id, `${player.player_name} (#${player.player_id})`)));
        const seasons = state.metadata.dataset.summary.leagues[String(league)]?.seasons || [];
        $('season-options').replaceChildren();
        for (const season of seasons) {
            const label = document.createElement('label');
            const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.value = season;
            label.append(checkbox, document.createTextNode(seasonLabel(season))); $('season-options').appendChild(label);
        }
        for (const id of ['season-start', 'season-end']) {
            $(id).replaceChildren(option('', 'Select season'), ...seasons.map(season => option(season, seasonLabel(season))));
        }
        conditions(); teamBadge();
    }
    async function loadMetadata(datasetId, generation = null) {
        const metadata = await request(`/api/trivia/metadata${datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : ''}`);
        if (generation !== null && generation !== state.generation) return;
        state.metadata = metadata;
        state.contextId = null;
        const data = state.metadata.dataset;
        $('dataset-date').textContent = new Date(data.created_at).toLocaleString('en-GB');
        $('dataset-date').title = `${data.dataset_id} | ${data.engine_version}`;
        $('dataset-summary').textContent = `${data.summary.fixtures.toLocaleString('en-GB')} matches | ${data.summary.timeline_valid.toLocaleString('en-GB')} verified timelines`;
        $('template').replaceChildren(...state.metadata.templates.map(template => option(template.template_key, template.label)));
        $('template').value = 'conditional_win_rate';
        $('league').replaceChildren(option('', 'Select competition'), ...Object.entries(data.summary.leagues).map(([id, league]) => option(id, league.name)));
        $('calculate').disabled = false;
        conditions(); populateLeague(); periodControls();
    }
    function invalidate() {
        state.generation++; state.controller?.abort(); state.result = null; state.saved = null; state.page = 0;
        state.entityId = null;
        $('ranking-section').hidden = true; $('ranking-reset').hidden = true;
        $('provenance-section').hidden = true; $('answer-stat').hidden = true; $('answer-scope').textContent = '';
        $('result-summary').hidden = true;
        $('kit-evidence').hidden=true; $('match-evidence-section').hidden=false;
        $('coverage-total-label').textContent=$('template').value==='kit_colour'?'Selected kits':'Selected matches';
        $('question-state').textContent = state.questionId ? 'New revision' : 'Unsaved';
        $('question-text').textContent = 'No calculation';
        for (const id of ['answer-value', 'coverage-total', 'coverage-matched', 'coverage-excluded']) $(id).textContent = '-';
        $('answer-fraction').textContent = ''; $('quality-warnings').replaceChildren();
        $('save-question').disabled = true; $('publish-question').disabled = true; $('answer-test').hidden = true;
        $('calculate').disabled = !state.metadata;
        $('grade-result').textContent = ''; renderEvidence();
    }
    function specification() {
        const mode = $('period-mode').value;
        let period;
        if (mode === 'seasons') {
            const seasons = [...$('season-options').querySelectorAll('input:checked')].map(input => Number(input.value));
            if (!seasons.length) throw new Error('Select at least one season.');
            period = {mode, seasons};
        } else if (mode === 'season_range') {
            period = {mode, start: Number($('season-start').value), end: Number($('season-end').value)};
            if (period.start > period.end) throw new Error('The start season must not follow the end season.');
        } else if (mode === 'dates') {
            period = {mode, start: $('date-start').value, end: $('date-end').value};
            if (period.start > period.end) throw new Error('The start date must not follow the end date.');
        } else if (mode === 'all') period = {mode};
        else throw new Error('Select a time period.');
        const spec = {template: $('template').value, league_id: Number($('league').value),
            venue: $('venue').value, period, minimum_sample: Number($('minimum-sample').value)};
        if ($('team').value && spec.template !== 'most_comeback_wins') spec.team_id = Number($('team').value);
        if (spec.template === 'player_goals') spec.player_id = Number($('player').value);
        if (spec.template === 'top_scorer') spec.name_policy = $('name-policy').value;
        if (['player_goals', 'top_scorer'].includes(spec.template)) spec.goal_filter = {
            after_minute: $('goal-minute').value === '' ? null : Number($('goal-minute').value),
            extra: Number($('goal-extra').value), role: $('goal-role').value, count: $('goal-count').value};
        if (spec.template === 'conditional_win_rate') spec.condition = {minute: Number($('minute').value), extra: Number($('extra').value),
            operator: $('operator').value, goal_difference: Number($('difference').value), clock: 'after_recorded_minute'};
        if (state.queryVersion) spec.query_version = state.queryVersion;
        if (!$('opponent').disabled && $('opponent').value) {
            const [kind, key, version] = $('opponent').value.split(':');
            if (kind === 'group') {
                const group = state.metadata.opponent_groups.find(g => g.group_key === key && g.version === Number(version));
                spec.opponents = {team_ids: group.team_ids.filter(id => id !== spec.team_id), group_key: key, group_version: Number(version)};
            } else spec.opponents = kind === 'custom' ? state.customOpponents : {team_ids: [Number(key)]};
        }
        if(spec.template==='kit_colour') {
            spec.kit_type=$('kit-type').value;spec.venue='all';spec.minimum_sample=1;
            if(period.mode!=='seasons'||period.seasons.length!==1)throw new Error('Select exactly one season for a kit question.');
        } else if(!$('weather-fields').disabled && $('weather-metric').value) {
            spec.weather={metric:$('weather-metric').value,operator:$('weather-operator').value,value:Number($('weather-value').value)};
        }
        if(spec.template==='kit_colour'||spec.weather){
            spec.context_id=state.contextId||state.metadata.context?.context_id;
            if(!spec.context_id)throw new Error('Build a context snapshot before using kit or weather questions.');
        }
        return spec;
    }
    function renderEvidence() {
        const filter = $('evidence-filter').value;
        const rows = (state.result?.evidence || []).filter(row => (filter === 'all' || row.disposition === filter) &&
            (state.entityId === null || (row.contributions || []).some(c => (c.player_id ?? c.team_id) === state.entityId)));
        const candidate = (state.result?.leaderboard || state.result?.analysis?.leaderboard || []).find(r => r.entity_id === state.entityId);
        $('evidence-scope').textContent = candidate ? `${candidate.name}: ${candidate.value} ${state.result.answer.unit || 'goals'} in ${rows.length} matching fixtures` : '';
        const pages = Math.max(1, Math.ceil(rows.length / 20)); state.page = Math.min(state.page, pages - 1);
        const body = $('evidence-body'); body.replaceChildren();
        for (const row of rows.slice(state.page * 20, state.page * 20 + 20)) {
            const tr = document.createElement('tr');
            const date = document.createElement('td');
            const standalone = $('trivia-page').dataset.standalone === 'true';
            const link = document.createElement(standalone ? 'span' : 'a');
            if (!standalone) { link.href = `/matches/${row.fixture_id}`; link.target = '_blank'; link.rel = 'noopener'; }
            link.textContent = new Date(row.match_date).toISOString().slice(0, 10); date.appendChild(link); tr.appendChild(date);
            let checkpoint = row.contributions ? row.contributions.filter(item => state.entityId === null || (item.player_id ?? item.team_id) === state.entityId).map(item => {
                if (item.comeback_win) return `${item.team_name}: comeback win`;
                const minute = Math.floor(item.clock_key / 1000), extra = item.clock_key % 1000;
                return `${item.player_name} ${minute}${extra ? `+${extra}` : ''}'${item.scorer_role === 'substitute' ? ' (sub)' : ''}`;
            }).join('; ') || '-' : row.checkpoint_for == null ? '-' : `${row.checkpoint_for}:${row.checkpoint_against}`;
            if(state.result?.specification.weather){
                const w=row.weather;
                checkpoint += w ? ` | ERA5: ${w.temperature_c??'?'} C; ${w.precipitation_mm??'?'} mm (preceding hour); ${w.sampled_at}` : ' | Weather unavailable';
            }
            const values = [row.match_label || row.opponent_name, row.match_label && !state.result?.specification.team_id ? '-' : row.is_home ? 'Home' : 'Away', checkpoint,
                row.match_label ? row.final_home == null ? '-' : `${row.final_home}:${row.final_away}` : row.goals_for == null ? '-' : `${row.goals_for}:${row.goals_against}`,
                row.disposition === 'excluded' ? row.reasons.map(reason => reasons[reason] || reason).join('; ') : row.result_label || row.result];
            for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.appendChild(td); }
            body.appendChild(tr);
        }
        if (!rows.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 6; td.textContent = 'No matches'; tr.appendChild(td); body.appendChild(tr); }
        $('evidence-page').textContent = rows.length ? `${state.page + 1} / ${pages} | ${rows.length} matches` : '0 matches';
        $('evidence-prev').disabled = state.page === 0; $('evidence-next').disabled = state.page + 1 >= pages;
    }
    function renderResult(data) {
        state.result = data;
        const answer = data.answer, coverage = data.coverage;
        const kit=data.specification.template==='kit_colour';
        $('coverage-total-label').textContent=kit?'Selected kits':'Selected matches';
        $('match-evidence-section').hidden=kit;$('kit-evidence').hidden=!kit;
        if(kit){
            const record=data.context_evidence||data.analysis?.context_evidence;
            $('kit-colour-label').textContent=answer.label||'Unclassified';
            $('kit-palette').textContent=(record?.palette||[]).map(p=>`${p.colour}: ${(p.share*100).toFixed(1)}%`).join(' | ');
            const swatches=answer.swatches||(answer.swatch?[answer.swatch]:[]);
            $('kit-colour-swatch').hidden=!swatches.length;
            $('kit-colour-swatch').replaceChildren(...swatches.map(colour=>{const node=document.createElement('span');node.className='trivia-colour-swatch';node.style.backgroundColor=colour;return node;}));
            $('kit-proof-image').hidden=!record?.image_url;
            if(record?.image_url)$('kit-proof-image').src=record.image_url;
            $('kit-source-link').hidden=!record?.source_url;
            if(record?.source_url)$('kit-source-link').href=record.source_url;
        }
        $('question-text').textContent = data.question_text;
        $('answer-value').textContent = answer.kind === 'entity' ? answer.label || 'Unavailable' : answer.value == null ? 'Unavailable' : `${answer.value}${answer.kind === 'percentage' ? '%' : ''}`;
        $('answer-value').classList.toggle('entity-answer', answer.kind === 'entity');
        const unit = answer.unit || (data.specification.template.includes('comeback') ? 'wins' : data.specification.goal_filter?.count === 'scoring_matches' ? 'scoring matches' : 'goals');
        const numeratorUnit = {loss_rate: 'losses', draw_rate: 'draws', points_per_game: 'points', goals_per_game: 'goals'}[data.specification.template] || 'wins';
        $('answer-fraction').textContent = kit?'Dominant shirt-body colour':answer.kind === 'entity' ? (answer.accepted?.length > 1 ? `${answer.accepted.length} joint leaders` : 'Leading player or team') : answer.denominator ? `${answer.numerator} ${numeratorUnit} / ${answer.denominator} matches` : `${answer.value ?? '-'} ${unit}`;
        const summary = data.summary || data.analysis?.summary;
        $('result-summary').hidden = !summary;
        $('result-summary').textContent = summary ? `${summary.played} played | ${summary.wins} wins | ${summary.draws} draws | ${summary.losses} losses | ${summary.goals_for}:${summary.goals_against} goals | ${summary.clean_sheets} clean sheets` : '';
        $('answer-stat').hidden = answer.kind !== 'entity'||kit;
        $('answer-stat-label').textContent = unit;
        $('answer-stat-value').textContent = answer.value ?? '-';
        $('answer-scope').textContent = `${coverage.eligible_matches} / ${coverage.requested_matches} ${kit?'kits':'matches'} eligible | ${coverage.publishable ? 'Checks passed' : 'Provisional result: publication blocked'}`;
        $('answer-scope').classList.toggle('provisional', !coverage.publishable);
        renderRanking(data, unit);
        const source = data.analysis?.source;
        $('provenance-section').hidden = !source;
        $('provenance-body').replaceChildren();
        if (source) for (const [label, value] of Object.entries({'Provider': source.name, 'Snapshot': source.snapshot_id,
            'Source fingerprint': source.source_hash, 'Engine': data.analysis.engine_version, 'Quality policy': data.analysis.policy_version,
            'Snapshot date': source.created_at, 'Verification': data.analysis.verification})) {
            const term = document.createElement('dt'), detail = document.createElement('dd');
            term.textContent = label; detail.textContent = value; $('provenance-body').append(term, detail);
        }
        if(data.analysis?.context_source) for(const [label,value] of Object.entries({'Weather snapshot':data.analysis.context_source.snapshot_id,'Weather source hash':data.analysis.context_source.source_hash,'Weather method':data.analysis.weather_policy})){
            const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=label;detail.textContent=value;$('provenance-body').append(term,detail);
        }
        $('answer-input').type = answer.kind === 'entity' ? 'text' : 'number';
        $('answer-input').value = '';
        $('coverage-total').textContent = coverage.requested_matches;
        $('coverage-matched').textContent = coverage.matched_matches;
        $('coverage-matched-label').textContent = data.specification.template === 'top_scorer' ? 'Matches with any scorer' : 'Matching condition';
        $('coverage-excluded').textContent = coverage.excluded_matches;
        const messages = {kit_missing_pixels:'Source pixels are not cached for this kit. Publication blocked.',kit_multicolour:'No single colour clearly dominates this shirt. Publication blocked.',kit_missing_record:'This exact season and kit set is missing. No fallback to another season.',kit_incomplete_pixels:'Incomplete source pixels. Publication blocked.',incomplete_coverage: `${coverage.excluded_matches} selected matches are excluded. Publication blocked: incomplete coverage.`,
            small_sample: `Sample below the required minimum of ${data.specification.minimum_sample}. Publication blocked.`,
            empty_sample: 'No eligible matches satisfy this definition. There is no answer.',
            no_ranking_winner: 'No qualifying goal or comeback. There is no ranking winner.',
            ambiguous_winner_name: 'Winner names are ambiguous in this source. Publication blocked.',
            incomplete_fixture_catalogue: 'The season does not contain the expected clubs and fixtures. Publication blocked.',
            duplicate_or_invalid_pairing: 'Duplicate or invalid home/away pairing. Publication blocked.',
            missing_reverse_fixture: 'A return fixture is missing. Publication blocked.',
            inconsistent_team_facts: 'Home and away match facts are missing or inconsistent. Publication blocked.',
            unverified_competition_format: 'The competition format has not been verified. Publication blocked.',
            season_not_complete: 'A selected season still contains unfinished matches. Select a completed period.',
            unsealed_dataset: 'This snapshot has not been sealed. Publication blocked.'};
        $('quality-warnings').replaceChildren();
        for (const warning of coverage.warnings) { const p = document.createElement('p'); p.textContent = messages[warning] || warning; $('quality-warnings').appendChild(p); }
        if (coverage.publishable) { const p = document.createElement('p'); p.className = 'valid'; p.textContent = 'Coverage and sample checks passed.'; $('quality-warnings').appendChild(p); }
        $('save-question').disabled = false;
        $('publish-question').disabled = !state.saved || state.saved.state !== 'draft' || !coverage.publishable;
        $('answer-test').hidden = state.saved?.state !== 'published';
        renderEvidence();
    }
    function renderRanking(data, unit) {
        const rows = data.leaderboard || data.analysis?.leaderboard || [];
        $('ranking-section').hidden = !rows.length;
        $('ranking-body').replaceChildren(); $('ranking-unit').textContent = unit;
        let rank = 0, last = null;
        for (const [index, row] of rows.entries()) {
            if (row.value !== last) rank = index + 1;
            last = row.value;
            const tr = document.createElement('tr');
            if (row.value === rows[0].value) tr.className = 'ranking-winner';
            for (const value of [rank, row.name]) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
            const metric = document.createElement('td'), number = document.createElement('strong'), bar = document.createElement('meter');
            number.textContent = row.value; bar.min = 0; bar.max = Math.max(rows[0].value, 1); bar.value = row.value;
            bar.setAttribute('aria-label', `${row.name}: ${row.value} ${unit}`); metric.append(number, bar); tr.append(metric);
            const action = document.createElement('td'), button = document.createElement('button');
            button.type = 'button'; button.textContent = 'Evidence'; button.setAttribute('aria-label', `Evidence for ${row.name}`);
            button.addEventListener('click', () => { state.entityId = row.entity_id; state.page = 0; $('evidence-filter').value = 'matched';
                $('ranking-reset').hidden = false; renderEvidence(); $('evidence-body').scrollIntoView({block: 'center', behavior: 'smooth'}); });
            action.append(button); tr.append(action); $('ranking-body').append(tr);
        }
    }
    $('ranking-reset').addEventListener('click', () => { state.entityId = null; state.page = 0; $('ranking-reset').hidden = true; renderEvidence(); });
    $('trivia-form').addEventListener('input', () => { invalidate(); conditions(); teamBadge(); });
    $('league').addEventListener('change', () => { populateLeague(); invalidate(); });
    $('period-mode').addEventListener('change', () => { periodControls(); invalidate(); });
    $('template').addEventListener('change', conditions);
    $('trivia-form').addEventListener('submit', async event => {
        event.preventDefault();
        try {
            const spec = specification(); invalidate();
            const generation = state.generation; state.controller = new AbortController();
            $('calculate').disabled = true; status('Calculating...');
            const data = await post('/api/trivia/evaluate', {specification: spec, dataset_id: state.metadata.dataset.dataset_id}, state.controller.signal);
            if (generation !== state.generation) return;
            renderResult(data); status('Calculation complete.');
            $('question-text').scrollIntoView({behavior: 'smooth', block: 'start'});
        } catch (error) { if (error.name !== 'AbortError') status(error.message, true); }
        finally { $('calculate').disabled = !state.metadata; }
    });
    $('save-question').addEventListener('click', async () => {
        if (!state.result) return;
        const generation = state.generation; const result = state.result;
        $('save-question').disabled = true;
        try {
            const saved = await post('/api/trivia/questions', {specification: result.specification, dataset_id: result.dataset_id, question_id: state.questionId});
            if (generation !== state.generation) { status('Previous calculation saved to the question library.'); return; }
            state.saved = saved; state.questionId = saved.question_id;
            $('question-state').textContent = `Draft | revision ${saved.revision}`;
            $('publish-question').disabled = !result.coverage.publishable;
            status('Draft saved with its data snapshot and match evidence.');
        } catch (error) { status(error.message, true); $('save-question').disabled = false; }
    });
    $('publish-question').addEventListener('click', async () => {
        if (!state.saved) return;
        const generation = state.generation, saved = state.saved;
        $('publish-question').disabled = true;
        try {
            await post(`/api/trivia/questions/${saved.version_id}/publish`, {});
            if (generation !== state.generation) return;
            saved.state = 'published'; $('question-state').textContent = `Published | revision ${saved.revision}`;
            $('answer-test').hidden = false; status('Question published.');
        } catch (error) { status(error.message, true); $('publish-question').disabled = false; }
    });
    $('answer-test').addEventListener('submit', async event => {
        event.preventDefault(); if (!state.saved) return;
        const generation = state.generation;
        try { const input = $('answer-input').value.trim();
            if (!input) return;
            const response = state.result.answer.kind === 'entity' ? {text: input} : {value: Number(input)};
            const grade = await post(`/api/trivia/questions/${state.saved.version_id}/grade`, response);
            if (generation === state.generation) $('grade-result').textContent = grade.correct ? 'Correct' : 'Incorrect';
        } catch (error) { status(error.message, true); }
    });
    function view(name) {
        const chosen = name === true ? 'library' : name === false ? 'editor' : name;
        for (const id of ['editor','library','audit','quizzes','query','training']) {
            if ($(`${id}-view`)) $(`${id}-view`).hidden = chosen !== id;
            if ($(`${id}-tab`)) $(`${id}-tab`).setAttribute('aria-pressed', String(chosen === id));
        }
    }
    document.addEventListener('trivia-view', event => view(event.detail));
    async function audit() {
        view('audit'); $('audit-body').replaceChildren();
        if (!state.metadata) { status('Wait for the dataset to load.', true); return; }
        try {
            const league = $('league').value || Object.keys(state.metadata.dataset.summary.leagues)[0];
            const data = await request(`/api/trivia/audit?league_id=${league}&dataset_id=${state.metadata.dataset.dataset_id}`);
            for (const row of data.seasons.slice().reverse()) {
                const tr = document.createElement('tr');
                for (const value of [seasonLabel(row.season), `${row.teams} / ${row.expected_teams ?? '?'}`,
                    `${row.fixtures} / ${row.expected_fixtures ?? '?'}`, row.finished, row.results, row.timelines, row.scorers,
                    row.problems.join(', ') || (row.finished !== row.fixtures ? 'Unfinished fixtures' : row.results !== row.fixtures ? 'Results require review' : row.scorers !== row.fixtures ? 'Events require review' : 'Checks passed')]) {
                    const td = document.createElement('td'); td.textContent = value; tr.append(td);
                }
                $('audit-body').append(tr);
            }
            status('');
        } catch (error) { status(error.message, true); }
    }
    $('audit-tab').addEventListener('click', audit); $('refresh-audit').addEventListener('click', audit);
    function populateSpec(spec) {
            $('template').value = spec.template; $('league').value = spec.league_id; populateLeague();
            $('team').value = spec.team_id || ''; $('player').value = spec.player_id || '';
            $('name-policy').value = spec.name_policy || 'exact-v1';
            state.queryVersion = spec.query_version || null; state.customOpponents = spec.opponents || null;
            state.contextId=spec.context_id||null;$('kit-type').value=spec.kit_type||'home';
            $('weather-metric').value=spec.weather?.metric||'';$('weather-operator').value=spec.weather?.operator||'gt';$('weather-value').value=spec.weather?.value??0;
            const opponents = spec.opponents;
            if (opponents?.group_key) $('opponent').value = `group:${opponents.group_key}:${opponents.group_version}`;
            else if (opponents?.team_ids.length === 1) $('opponent').value = `team:${opponents.team_ids[0]}`;
            else if (opponents) { $('opponent').append(option('custom', 'Selected opponent IDs: ' + opponents.team_ids.join(', '))); $('opponent').value = 'custom'; }
            $('goal-minute').value = spec.goal_filter?.after_minute ?? '';
            $('goal-extra').value = spec.goal_filter?.extra ?? 0;
            $('goal-role').value = spec.goal_filter?.role || 'all';
            $('goal-count').value = spec.goal_filter?.count || 'goals';
            $('venue').value = spec.venue; $('minimum-sample').value = spec.minimum_sample;
            $('period-mode').value = spec.period.mode; periodControls();
            if (spec.period.mode === 'seasons') for (const input of $('season-options').querySelectorAll('input')) input.checked = spec.period.seasons.includes(Number(input.value));
            if (spec.period.mode === 'season_range') { $('season-start').value = spec.period.start; $('season-end').value = spec.period.end; }
            if (spec.period.mode === 'dates') { $('date-start').value = spec.period.start; $('date-end').value = spec.period.end; }
            if (spec.condition) { $('minute').value = spec.condition.minute; $('extra').value = spec.condition.extra; $('operator').value = spec.condition.operator; $('difference').value = spec.condition.goal_difference; }
            conditions(); teamBadge();
    }
    document.addEventListener('trivia-query-result', async event => {
        invalidate(); state.questionId = null;
        const generation = state.generation, result = event.detail;
        try {
            await loadMetadata(result.dataset_id, generation);
            if (generation !== state.generation) return;
            populateSpec(result.specification); renderResult(result);
            $('question-state').textContent = 'Unsaved'; view('editor'); status('Query loaded with its original snapshot and exact opponents.');
        } catch (error) { status(error.message, true); }
    });
    async function openQuestion(versionId) {
        try {
            invalidate(); const generation = state.generation;
            const question = await request(`/api/trivia/questions/${versionId}`);
            if (generation !== state.generation) return;
            await loadMetadata(question.dataset_id, generation);
            if (generation !== state.generation) return;
            populateSpec(question.specification);
            state.questionId = question.question_id; state.saved = question;
            renderResult(question); $('save-question').disabled = true;
            $('question-state').textContent = `${question.state} | revision ${question.revision}`;
            view(false); status('Saved version loaded from its original snapshot.');
        } catch (error) { status(error.message, true); }
    }
    async function library() {
        view(true); status('');
        try {
            const data = await request('/api/trivia/questions'); $('question-list').replaceChildren();
            if (!data.questions.length) $('question-list').textContent = 'No saved questions';
            for (const item of data.questions) {
                const row = document.createElement('article'); row.className = 'trivia-library-row';
                const text = document.createElement('div'), p = document.createElement('p'), detail = document.createElement('small');
                p.textContent = item.question_text; detail.textContent = `${item.state} | revision ${item.revision} | ${new Date(item.created_at).toLocaleDateString('en-GB')}`;
                text.append(p, detail); const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Open';
                button.addEventListener('click', () => openQuestion(item.version_id)); row.append(text, button); $('question-list').appendChild(row);
            }
        } catch (error) { status(error.message, true); }
    }
    $('editor-tab').addEventListener('click', () => view(false)); $('library-tab').addEventListener('click', library);
    $('refresh-library').addEventListener('click', library);
    $('new-question').addEventListener('click', async () => {
        invalidate(); state.questionId = null; state.queryVersion = null; state.customOpponents = null; $('trivia-form').reset();
        try { await loadMetadata(); $('question-state').textContent = 'Unsaved'; status(''); } catch (error) { status(error.message, true); }
    });
    $('evidence-filter').addEventListener('change', () => { state.page = 0; renderEvidence(); });
    $('evidence-prev').addEventListener('click', () => { state.page--; renderEvidence(); });
    $('evidence-next').addEventListener('click', () => { state.page++; renderEvidence(); });
    loadMetadata().then(() => status('')).catch(error => status(error.message, true));
})();
