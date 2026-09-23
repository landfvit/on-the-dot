(async function () {
    const page = document.getElementById('match-page');
    if (!page) return;
    const $ = id => document.getElementById(id);
    const scoring = new Set(['Normal Goal', 'Penalty', 'Own Goal']);
    let data;
    const node = (tag, text, className) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; };
    const minute = e => e.elapsed_minute == null ? '?' : `${e.elapsed_minute}${e.extra_minute ? `+${e.extra_minute}` : ''}'`;
    function player(id, name) {
        const link = node(id ? 'a' : 'span', name || 'Unknown player');
        if (id) link.href = `/players/${id}?season=${data.fixture.season}`;
        return link;
    }
    function sourceLink(url, label) {
        const parsed = new URL(url, location.origin);
        const n = node(['http:', 'https:'].includes(parsed.protocol) ? 'a' : 'span', label);
        if (n.tagName === 'A') { n.href = parsed.href; n.target = '_blank'; n.rel = 'noopener noreferrer'; }
        return n;
    }
    function fact(label, value, detail, source) {
        const group = node('div'), dd = node('dd', value);
        if (detail) dd.append(node('small', detail));
        if (source) { const small = node('small'); small.append(sourceLink(source, 'Source')); dd.append(small); }
        group.append(node('dt', label), dd); $('match-environment').append(group);
    }
    function renderEvents() {
        const filter = $('event-filter').value;
        const events = data.events.filter(e => filter === 'all' || e.event_type === filter);
        $('match-events-list').replaceChildren();
        if (!events.length) {
            $('match-events-list').append(node('li', data.events.length ? 'No matching events.' : 'No recorded events available.'));
            return;
        }
        for (const event of events) {
            const row = node('li', null, 'match-event');
            const portrait = node('span', (event.player_name || '?').split(/\s+/).slice(0, 2).map(p => p[0]).join(''), 'event-portrait');
            portrait.setAttribute('aria-hidden', 'true');
            if (event.photo_url) {
                const img = node('img'); img.src = event.photo_url; img.alt = ''; img.loading = 'lazy';
                img.addEventListener('error', () => img.remove(), {once: true}); portrait.textContent = ''; portrait.append(img);
            }
            const desc = node('div', null, 'event-description');
            const teamName = event.side === 'home' ? data.fixture.home_name : event.side === 'away' ? data.fixture.away_name : 'Unknown team';
            let label = event.event_detail || event.event_type || 'Event';
            if (event.event_type === 'subst') label = 'Substitution';
            const kind = event.event_type === 'Card' ? (/red/i.test(label) ? 'red' : 'card') : '';
            desc.append(node('div', `${label} | ${teamName}`, `event-label ${kind}`));
            if (event.event_type === 'subst') {
                const incoming = node('div', 'In: '); incoming.append(player(event.assist_player_id, event.assist_player_name));
                const outgoing = node('small', 'Out: '); outgoing.append(player(event.player_id, event.player_name)); desc.append(incoming, outgoing);
            } else {
                desc.append(player(event.player_id, event.player_name));
                if (event.event_type === 'Goal' && event.event_detail !== 'Own Goal' && event.assist_player_name) {
                    const assist = node('small', 'Assist: '); assist.append(player(event.assist_player_id, event.assist_player_name)); desc.append(assist);
                }
            }
            if (event.comments) desc.append(node('small', event.comments));
            row.append(node('time', minute(event)), portrait, desc, node('span', event.score ? event.score.join(' : ') : '', 'event-score'));
            $('match-events-list').append(row);
        }
    }
    try {
        const response = await fetch(`/api/fixtures/${page.dataset.fixtureId}/context`);
        if (!response.ok) throw new Error('Match context unavailable');
        data = await response.json();
        const valid = data.quality.timeline_valid;
        $('events-quality').textContent = valid
            ? 'API-Football | Goal totals checked against half-time and full-time scores.'
            : data.fixture.status === 'NS' ? 'Match has not started.'
            : 'Source events may be incomplete or contain unresolved VAR decisions. Score progression is unavailable.';
        $('events-quality').classList.toggle('warning', !valid && data.fixture.status !== 'NS');
        for (const side of ['home', 'away']) {
            const list = node('div');
            for (const event of data.events.filter(e => e.side === side && e.event_type === 'Goal' && scoring.has(e.event_detail))) {
                const line = node('div'); line.append(player(event.player_id, event.player_name), document.createTextNode(` ${minute(event)}${event.event_detail === 'Penalty' ? ' (pen)' : event.event_detail === 'Own Goal' ? ' (OG)' : ''}`));
                list.append(line);
            }
            if (!valid && list.children.length) list.append(node('small', 'Unverified source events'));
            $('match-scorers').append(list);
        }
        fact('Stadium', data.fixture.venue_name || 'Unavailable', data.fixture.city);
        fact('Referee', data.fixture.referee || 'Unavailable');
        const a = data.attendance;
        fact('Attendance', a ? Number(a.attendance).toLocaleString('en-GB') : 'Unavailable',
            a?.occupancy_percent != null ? `${a.occupancy_percent}% of capacity at this match` : null, a?.source_url);
        const w = data.weather;
        if (w) {
            const temp = w.temperature_c == null ? 'Temperature unavailable' : `${w.temperature_c.toFixed(1)} °C`;
            const detail = [`Open-Meteo / ${w.model} reanalysis`, new Date(w.sampled_at).toLocaleString('en-GB', {timeZone: 'UTC'}) + ' UTC',
                w.wind_kmh == null ? null : `Wind ${w.wind_kmh.toFixed(1)} km/h`,
                w.precipitation_mm == null ? null : `Preceding-hour rain/snow ${w.precipitation_mm.toFixed(1)} mm`].filter(Boolean).join(' | ');
            fact('Weather near kickoff', temp, detail, w.source_url);
        } else fact('Weather near kickoff', 'Unavailable');
        for (const rest of data.league_rest) fact(rest.team_id === data.fixture.home_team_id ? data.fixture.home_name : data.fixture.away_name,
            `${rest.days} days since previous league match`);
        $('event-filter').addEventListener('change', renderEvents);
        renderEvents();
    } catch (error) { $('events-quality').textContent = 'Could not load match events and context. Reload to try again.'; }
})();
