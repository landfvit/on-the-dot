(async function () {
    const page = document.getElementById('team-page');
    const stadium = document.getElementById('team-stadium');
    const capacity = document.getElementById('team-capacity');
    const staff = document.getElementById('team-coaches');
    function dateLabel(value) {
        if (!value) return '';
        const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
        return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});
    }
    try {
        const response = await fetch(`/api/teams/${page.dataset.teamId}/context?season=${page.dataset.season}`);
        if (!response.ok) throw new Error('Team context unavailable');
        const data = await response.json();
        stadium.textContent = data.venue?.venue_name || 'Not available';
        stadium.title = data.venue?.city || '';
        capacity.textContent = Number(data.venue?.capacity) > 0
            ? Number(data.venue.capacity).toLocaleString('en-GB') : 'Not available';
        capacity.title = data.venue?.capacity_updated_at
            ? `Latest capacity supplied by API-Football, updated ${dateLabel(data.venue.capacity_updated_at)}; not a historical capacity estimate.` : '';
        staff.replaceChildren();
        if (!data.coaches.length) {
            staff.textContent = 'No coach records available for this season.';
            return;
        }
        for (const [index, coach] of data.coaches.entries()) {
            const fullName = coach.first_name && coach.last_name ? `${coach.first_name} ${coach.last_name}` : '';
            const name = fullName && /\b[A-Z]\./.test(coach.coach_name || '')
                ? fullName : coach.coach_name || fullName || 'Unknown coach';
            const row = document.createElement('article');
            row.className = 'team-coach';
            const portrait = document.createElement('div');
            portrait.className = 'team-coach-portrait';
            const initials = name.split(/\s+/).slice(0, 2).map(word => word[0]).join('');
            portrait.textContent = initials;
            portrait.setAttribute('aria-hidden', 'true');
            if (coach.photo_url) {
                const image = document.createElement('img');
                image.src = coach.photo_url;
                image.alt = '';
                image.width = 64;
                image.height = 64;
                image.loading = 'lazy';
                image.addEventListener('error', () => { portrait.textContent = initials; }, {once: true});
                portrait.replaceChildren(image);
            }
            const details = document.createElement('div');
            const role = document.createElement('span');
            role.className = 'team-coach-role';
            role.textContent = data.coach_source === 'lineups'
                ? (index === 0 ? 'Latest recorded coach' : 'Earlier this season') : 'Coach';
            const heading = document.createElement('h4');
            heading.textContent = name;
            const nationality = document.createElement('p');
            nationality.textContent = coach.nationality || 'Nationality unavailable';
            const record = document.createElement('p');
            if (data.coach_source === 'lineups') {
                record.textContent = `${coach.matches} recorded ${coach.matches === 1 ? 'match' : 'matches'} | Last: ${dateLabel(coach.last_match)}`;
            } else {
                record.textContent = `From ${dateLabel(coach.start_date)}${coach.end_date ? ` to ${dateLabel(coach.end_date)}` : ''}`;
            }
            details.append(role, heading, nationality, record);
            row.append(portrait, details);
            staff.appendChild(row);
        }
    } catch {
        stadium.textContent = 'Not available';
        capacity.textContent = 'Not available';
        staff.textContent = 'Could not load coaching staff.';
    }
})();
