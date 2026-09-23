(async function () {
    const page = document.getElementById('team-page');
    if (!page) return;
    const $ = id => document.getElementById(id);
    const node = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
    function metric(target, label, value, detail) {
        const item = node('div'); item.append(node('span', label), node('strong', value ?? 'Unavailable'));
        if (detail) item.append(node('small', detail)); $(target).append(item);
    }
    try {
        const response = await fetch(`/api/teams/${page.dataset.teamId}/insights?season=${page.dataset.season}`);
        if (!response.ok) throw new Error();
        const data = await response.json();
        function results() {
            const r = data.splits[$('insights-split').value];
            $('insights-results').replaceChildren();
            $('insights-status').textContent = `${r.matches} finished league matches`;
            metric('insights-results', 'W / D / L', `${r.wins} / ${r.draws} / ${r.losses}`);
            metric('insights-results', 'Points per match', r.points_per_match);
            metric('insights-results', 'Goals for / against', `${r.goals_for} / ${r.goals_against}`);
            metric('insights-results', 'Win rate', r.matches ? `${(100 * r.wins / r.matches).toFixed(1)}%` : null, `${r.wins} wins / ${r.matches} matches`);
        }
        $('insights-split').addEventListener('change', results); results();
        $('insights-coverage').textContent = `${data.timeline_matches} / ${data.results_matches} finished matches with checked goal timelines. ${data.excluded_timelines} excluded. Same-minute goals follow source order.`;
        metric('insights-situations', 'Points gained after trailing', data.points_gained, `${data.matches_trailed} matches trailed`);
        metric('insights-situations', 'Points dropped after leading', data.points_dropped, `${data.matches_led} matches led`);
        for (const [key, label] of [['scored_first', 'Scored first'], ['conceded_first', 'Conceded first']]) {
            const s = data.first_goal[key], row = node('div'); row.className = 'insights-first-row';
            row.append(node('span', label), node('strong', `${s.wins} W / ${s.draws} D / ${s.losses} L (${s.matches} matches)`)); $('insights-first-goal').append(row);
        }
        const max = Math.max(1, ...data.goal_intervals.flatMap(b => [b.for, b.against]));
        if (!data.goal_intervals.length) $('insights-goal-periods').textContent = 'No verified goal timelines available.';
        else $('insights-goal-periods').append(node('p', 'Scored / conceded | 45+ and 90+ included in their respective halves'));
        for (const b of data.goal_intervals) {
            const row = node('div'), bars = node('div'); row.className = 'insights-goal-row'; bars.className = 'insights-bars';
            for (const side of ['for', 'against']) {
                const track = node('div'), bar = node('div'); track.className = 'insights-track'; bar.className = `insights-bar ${side}`;
                bar.style.width = `${100 * b[side] / max}%`; track.append(bar); bars.append(track);
            }
            row.append(node('span', b.label), bars, node('strong', `${b.for} / ${b.against}`)); $('insights-goal-periods').append(row);
        }
    } catch (error) { $('insights-status').textContent = 'Could not load team insights. Reload to try again.'; }
})();
