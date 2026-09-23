(function () {
    const page = document.getElementById('player-page');
    if (!page) return;
    const $ = id => document.getElementById(id);
    const tabs = [...document.querySelectorAll('[data-player-tab]')];
    const node = (tag, text, className) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; };
    const label = season => `${season}/${String(Number(season) + 1).slice(-2)}`;
    const dateLabel = value => {
        if (!value) return 'Not recorded';
        const date = new Date(`${String(value).slice(0, 10)}T12:00:00Z`);
        return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
    };
    let data = null, loading = false;

    function activate(name) {
        const selected = tabs.find(tab => tab.dataset.playerTab === name) || tabs[0];
        for (const tab of tabs) {
            const active = tab === selected;
            tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1;
            $(tab.getAttribute('aria-controls')).hidden = !active;
        }
    }
    for (const [index, tab] of tabs.entries()) {
        tab.addEventListener('click', () => { activate(tab.dataset.playerTab); history.replaceState(null, '', `#${tab.dataset.playerTab}`); });
        tab.addEventListener('keydown', event => {
            const next = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1}[event.key];
            if (next === undefined) return;
            event.preventDefault(); tabs[next].click(); tabs[next].focus();
        });
    }
    window.addEventListener('hashchange', () => activate(location.hash.slice(1)));
    activate(location.hash.slice(1));

    function clubLink(club, requestedSeason, leagueId) {
        const name = club.name || club.team_name || 'Unknown club';
        const available = club.profile_seasons || [];
        const season = leagueId === 39 ? requestedSeason : available.includes(requestedSeason) ? requestedSeason : available[0];
        const link = node(club.team_id && season != null ? 'a' : 'span', null, 'player-history-club');
        if (link.tagName === 'A') { link.href = `/teams/${club.team_id}?season=${season}`; link.title = `Premier League profile: ${label(season)}`; }
        const fallback = () => node('span', name.split(/\s+/).slice(0, 2).map(word => word[0]).join(''), 'history-logo-fallback');
        if (club.logo_url) {
            const img = node('img', null, 'entity-team-logo-inline'); img.src = club.logo_url; img.alt = ''; img.width = 24; img.height = 24; img.loading = 'lazy';
            img.addEventListener('error', () => { img.hidden = true; link.prepend(fallback()); }, {once: true});
            link.append(img);
        } else link.append(fallback());
        link.append(node('span', name));
        return link;
    }
    function ratingCell(record) {
        const cell = node('td', record.rating == null ? '\u2014' : Number(record.rating).toFixed(2));
        if (record.rating_source === 'match_ratings') {
            const sample = `${record.rated_matches}${record.appearances == null ? '' : ` / ${record.appearances}`} rated`;
            cell.append(node('small', sample));
            cell.title = 'Arithmetic mean of available ratings for matches the player entered; unused substitutes excluded.';
        } else if (record.rating_source === 'provider_season') cell.append(node('small', 'Provider season rating'));
        return cell;
    }
    function metrics(row, record) {
        for (const field of ['appearances', 'goals', 'assists', 'yellow_cards', 'red_cards']) {
            const cell = node('td', record[field] == null ? '\u2014' : Number(record[field]).toLocaleString('en-GB'));
            if (record[field] == null) cell.title = 'Not available in the source data';
            if (field === 'appearances' && record.warnings?.length) cell.append(node('small', record.warnings.includes('partial_appearance_coverage') ? 'Recorded sample' : 'Source conflict', 'history-warning'));
            row.append(cell);
        }
        row.append(ratingCell(record));
    }
    function seasons() {
        const records = data.seasons.filter(row => String(row.league_id) === $('player-history-league').value);
        $('player-seasons-body').replaceChildren();
        $('player-seasons-status').textContent = records.length ? `${records.length} available seasons | ${data.source}` : 'No season statistics available.';
        for (const record of records) {
            const row = node('tr', null, 'history-season-total'), season = node('th'); season.scope = 'row';
            const link = node(record.league_id === 39 ? 'a' : 'span', label(record.season));
            if (link.tagName === 'A') link.href = `/players/${page.dataset.playerId}?season=${record.season}#overview`;
            season.append(link); row.append(season);
            const club = node('td');
            if (record.clubs.length === 1) club.append(clubLink(record.clubs[0], record.season, record.league_id));
            else club.textContent = `${record.clubs.length} clubs combined`;
            row.append(club); metrics(row, record); $('player-seasons-body').append(row);
            if (record.clubs.length > 1) for (const team of record.clubs) {
                const detail = node('tr', null, 'history-club-row'), teamCell = node('td'); teamCell.append(clubLink(team, record.season, record.league_id));
                detail.append(node('td', label(record.season)), teamCell); metrics(detail, team); $('player-seasons-body').append(detail);
            }
        }
    }
    function transferKind(value) {
        if (/return|back from/i.test(value)) return 'return';
        if (/loan/i.test(value)) return 'loan';
        if (/^(n\/a|unknown|-)$/i.test(value)) return 'unknown';
        return 'permanent';
    }
    function transferLabel(value) { return transferKind(value) === 'unknown' ? 'Not disclosed' : value; }
    function transferStatus() {
        const status = data.transfer_import;
        return status ? `${data.source} | Last ${status.status === 'success' ? 'import' : 'import attempt'}: ${dateLabel(status.imported_at)}${status.status === 'failed' ? ' (failed, stored records shown)' : ''}` : `${data.source} | Import status unavailable`;
    }
    function transfers() {
        const selected = $('player-transfer-filter').value;
        const records = data.transfers.filter(row => selected === 'all' || transferKind(row.type) === selected);
        $('player-transfers-body').replaceChildren();
        $('player-transfers-status').textContent = `${transferStatus()} | ${records.length} recorded moves${data.duplicate_transfer_records ? ` | ${data.duplicate_transfer_records} duplicate source records merged` : ''}`;
        if (!records.length) {
            const row = node('tr'), cell = node('td', data.transfers.length ? 'No matching transfers.' : 'No transfer records available.'); cell.colSpan = 4; row.append(cell); $('player-transfers-body').append(row);
        }
        for (const transfer of records) {
            const row = node('tr'), date = node('td', dateLabel(transfer.date));
            if (transfer.upcoming) date.append(node('small', 'Upcoming / provider record'));
            const from = node('td'), to = node('td'), type = node('td');
            const year = transfer.date ? Number(transfer.date.slice(0, 4)) - (Number(transfer.date.slice(5, 7)) < 7 ? 1 : 0) : null;
            from.append(clubLink(transfer.out, year)); to.append(clubLink(transfer.in, year));
            type.append(node('span', transferLabel(transfer.type), `player-transfer-type ${transferKind(transfer.type)}`));
            row.append(date, from, to, type); $('player-transfers-body').append(row);
        }
    }
    function clubs() {
        $('player-clubs-list').replaceChildren();
        $('player-clubs-status').textContent = `${transferStatus()} | Recorded club spells; missing boundaries and source conflicts are marked.`;
        if (!data.clubs.length) { $('player-clubs-list').append(node('li', 'No club history available.')); return; }
        for (const spell of data.clubs) {
            const row = node('li'), dates = node('div', null, 'history-club-dates'), details = node('div', null, 'history-club-detail');
            if (spell.recorded_seasons) {
                dates.append(node('strong', 'Season records'), node('span', spell.recorded_seasons.map(label).join(', ')));
            } else {
                dates.append(node('strong', spell.arrival_dates.length ? spell.arrival_dates.map(dateLabel).join(' / ') : 'Arrival not recorded'),
                    node('span', spell.end_date ? `Until ${dateLabel(spell.end_date)}` : 'Departure not recorded'));
            }
            details.append(clubLink(spell.club));
            if (spell.entry_type) details.append(node('p', transferLabel(spell.entry_type)));
            if (spell.arrival_dates.length > 1) details.append(node('p', 'Conflicting arrival dates in the source.'));
            else if (spell.uncertain) details.append(node('p', 'Incomplete transfer history.'));
            row.append(dates, details); $('player-clubs-list').append(row);
        }
    }
    async function load() {
        if (loading) return;
        loading = true; $('player-history-retry').disabled = true;
        try {
            const response = await fetch(`/api/players/${page.dataset.playerId}/history`);
            if (!response.ok) throw new Error();
            data = await response.json();
            const competitions = new Map(data.seasons.map(row => [row.league_id, row.league_name]));
            const select = $('player-history-league'); select.replaceChildren();
            for (const [id, name] of competitions) { const option = node('option', name); option.value = id; select.append(option); }
            if (!competitions.size) select.append(node('option', 'No competition records'));
            if (competitions.has(39)) select.value = '39';
            select.disabled = competitions.size <= 1;
            $('player-history-error').hidden = true;
            seasons(); clubs(); transfers();
        } catch (error) {
            $('player-history-error-text').textContent = 'Could not load player history. The overview remains available.';
            $('player-history-error').hidden = false;
            for (const name of ['seasons', 'clubs', 'transfers']) $(`player-${name}-status`).textContent = 'History unavailable.';
        } finally { loading = false; $('player-history-retry').disabled = false; }
    }
    $('player-history-league').addEventListener('change', seasons);
    $('player-transfer-filter').addEventListener('change', () => { if (data) transfers(); });
    $('player-history-retry').addEventListener('click', load);
    load();
})();
