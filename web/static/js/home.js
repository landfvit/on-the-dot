const seasonSelect = document.getElementById(
    "season-select"
);

const matchesContainer = document.getElementById(
    "matches-container"
);

const matchSummary = document.getElementById(
    "match-summary"
);

const apiIndicator = document.getElementById(
    "api-indicator"
);

const sidebarMatchCount = document.getElementById(
    "sidebar-match-count"
);

const matchesTab = document.getElementById(
    "matches-tab"
);

const standingsTab = document.getElementById(
    "standings-tab"
);

const teamsTab = document.getElementById(
    "teams-tab"
);

const sidebarMatches = document.getElementById(
    "sidebar-matches"
);

const sidebarStandings = document.getElementById(
    "sidebar-standings"
);

const sidebarTeams = document.getElementById(
    "sidebar-teams"
);

const matchesView = document.getElementById(
    "matches-view"
);

const standingsView = document.getElementById(
    "standings-view"
);

const teamsView = document.getElementById(
    "teams-view"
);

const standingsBody = document.getElementById(
    "standings-body"
);

const standingsSummary = document.getElementById(
    "standings-summary"
);

const teamsGrid = document.getElementById(
    "teams-grid"
);

const teamsSummary = document.getElementById(
    "teams-summary"
);


let activeView = "matches";


async function fetchJSON(url) {
    const response = await fetch(
        url
    );

    if (!response.ok) {
        throw new Error(
            `request failed: ${response.status}`
        );
    }

    return response.json();
}


function formatSeason(season) {
    return `${season}/${String(
        season + 1
    ).slice(-2)}`;
}


function formatMatchDate(value) {
    const date = new Date(
        value
    );

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric"
        }
    ).format(
        date
    );
}


function getDateKey(value) {
    const date = new Date(
        value
    );

    return date.toLocaleDateString(
        "en-CA"
    );
}


function getMatchStatus(fixture) {
    if (fixture.status === "FT") {
        return "FT";
    }

    const date = new Date(
        fixture.match_date
    );

    return date.toLocaleTimeString(
        [],
        {
            hour: "2-digit",
            minute: "2-digit"
        }
    );
}


function getScore(fixture) {
    if (
        fixture.home_goals === null
        || fixture.away_goals === null
    ) {
        return {
            home: "-",
            away: "-"
        };
    }

    return {
        home: fixture.home_goals,
        away: fixture.away_goals
    };
}


function groupFixturesByDate(fixtures) {
    const groups = new Map();

    for (const fixture of fixtures) {
        const key = getDateKey(
            fixture.match_date
        );

        if (!groups.has(key)) {
            groups.set(
                key,
                []
            );
        }

        groups.get(
            key
        ).push(
            fixture
        );
    }

    return groups;
}


function createTeamEntityLink(
    teamId,
    teamName,
    season
) {
    const link = document.createElement(
        "a"
    );

    link.href =
        `/teams/${teamId}?season=${season}`;

    link.className =
        "entity-trigger match-team-link";

    link.textContent =
        teamName;

    link.dataset.entityType =
        "team";

    link.dataset.entityId =
        teamId;

    link.dataset.season =
        season;

    link.style.color =
        "inherit";

    link.style.textDecoration =
        "none";

    return link;
}


function createMatchRow(fixture) {
    const row = document.createElement(
        "div"
    );

    row.className =
        "match-row";

    row.setAttribute(
        "role",
        "link"
    );

    row.setAttribute(
        "tabindex",
        "0"
    );

    const score = getScore(
        fixture
    );

    const dataStatus =
        fixture.data_status
        || "missing";

    row.innerHTML = `
        <div class="match-status">
            ${getMatchStatus(fixture)}
        </div>

        <div class="team home"></div>

        <div class="score">
            <span>
                ${score.home}
            </span>

            <span class="score-divider">
                -
            </span>

            <span>
                ${score.away}
            </span>
        </div>

        <div class="team away"></div>

        <div class="data-status ${dataStatus}">
            ${dataStatus}
        </div>
    `;

    const homeTeamContainer =
        row.querySelector(
            ".team.home"
        );

    const awayTeamContainer =
        row.querySelector(
            ".team.away"
        );

    homeTeamContainer.appendChild(
        createTeamEntityLink(
            fixture.home_team_id,
            fixture.home_team,
            fixture.season
        )
    );

    awayTeamContainer.appendChild(
        createTeamEntityLink(
            fixture.away_team_id,
            fixture.away_team,
            fixture.season
        )
    );

    row.addEventListener(
        "click",
        event => {
            if (
                event.target.closest(
                    "a"
                )
            ) {
                return;
            }

            window.location.href =
                `/matches/${fixture.fixture_id}`;
        }
    );

    row.addEventListener(
        "keydown",
        event => {
            if (
                event.target.closest(
                    "a"
                )
            ) {
                return;
            }

            if (
                event.key === "Enter"
                || event.key === " "
            ) {
                event.preventDefault();

                window.location.href =
                    `/matches/${fixture.fixture_id}`;
            }
        }
    );

    return row;
}


function renderFixtures(fixtures) {
    matchesContainer.innerHTML = "";

    if (fixtures.length === 0) {
        matchesContainer.innerHTML = `
            <div class="empty-card">
                No matches found.
            </div>
        `;

        return;
    }

    const groups =
        groupFixturesByDate(
            fixtures
        );

    for (
        const fixturesForDay
        of groups.values()
    ) {
        const matchDay =
            document.createElement(
                "div"
            );

        matchDay.className =
            "match-day";

        const header =
            document.createElement(
                "div"
            );

        header.className =
            "match-day-header";

        header.textContent =
            formatMatchDate(
                fixturesForDay[0].match_date
            );

        matchDay.appendChild(
            header
        );

        for (
            const fixture
            of fixturesForDay
        ) {
            matchDay.appendChild(
                createMatchRow(
                    fixture
                )
            );
        }

        matchesContainer.appendChild(
            matchDay
        );
    }
}


function formatGoalDifference(value) {
    if (value > 0) {
        return `+${value}`;
    }

    return String(
        value
    );
}


function getGoalDifferenceClass(value) {
    if (value > 0) {
        return "goal-difference-positive";
    }

    if (value < 0) {
        return "goal-difference-negative";
    }

    return "";
}


function renderStandings(
    standings,
    season
) {
    standingsBody.innerHTML = "";

    if (standings.length === 0) {
        standingsBody.innerHTML = `
            <tr>
                <td
                    colspan="10"
                    class="standings-message"
                >
                    No standings available.
                </td>
            </tr>
        `;

        return;
    }

    for (const team of standings) {
        const row =
            document.createElement(
                "tr"
            );

        const goalDifferenceClass =
            getGoalDifferenceClass(
                team.goal_difference
            );

        const teamUrl =
            `/teams/${team.team_id}?season=${season}`;

        row.innerHTML = `
            <td class="standings-position">
                ${team.position}
            </td>

            <td class="standings-team">
                <a
                    href="${teamUrl}"
                    class="standings-team-link"
                >
                    ${team.team_name}
                </a>
            </td>

            <td>
                ${team.played}
            </td>

            <td class="optional-column">
                ${team.wins}
            </td>

            <td class="optional-column">
                ${team.draws}
            </td>

            <td class="optional-column">
                ${team.losses}
            </td>

            <td class="optional-column">
                ${team.goals_for}
            </td>

            <td class="optional-column">
                ${team.goals_against}
            </td>

            <td class="${goalDifferenceClass}">
                ${formatGoalDifference(
                    team.goal_difference
                )}
            </td>

            <td class="standings-points">
                ${team.points}
            </td>
        `;

        row.addEventListener(
            "click",
            event => {
                if (
                    event.target.closest(
                        "a"
                    )
                ) {
                    return;
                }

                window.location.href =
                    teamUrl;
            }
        );

        standingsBody.appendChild(
            row
        );
    }
}


function getTeamInitials(name) {
    const words = name.split(
        " "
    );

    if (words.length === 1) {
        return words[0]
            .slice(
                0,
                2
            )
            .toUpperCase();
    }

    return words
        .slice(
            0,
            2
        )
        .map(
            word => word[0]
        )
        .join("")
        .toUpperCase();
}


function renderTeams(
    standings,
    season
) {
    teamsGrid.innerHTML = "";

    if (standings.length === 0) {
        teamsGrid.innerHTML = `
            <div class="empty-card">
                No teams found.
            </div>
        `;

        return;
    }

    for (const team of standings) {
        const teamUrl =
            `/teams/${team.team_id}?season=${season}`;

        const card =
            document.createElement(
                "a"
            );

        card.className =
            "team-card";

        card.href =
            teamUrl;

        card.innerHTML = `
            <div class="team-card-badge">
                ${getTeamInitials(
                    team.team_name
                )}
            </div>

            <div class="team-card-content">
                <h3 class="team-card-name">
                    ${team.team_name}
                </h3>

                <div class="team-card-meta">
                    <span>
                        ${team.points} pts
                    </span>

                    <span>
                        ${formatGoalDifference(
                            team.goal_difference
                        )} GD
                    </span>
                </div>
            </div>

            <div class="team-card-position">
                #${team.position}
            </div>
        `;

        teamsGrid.appendChild(
            card
        );
    }
}


async function loadHealth() {
    try {
        await fetchJSON(
            "/api/health"
        );

        apiIndicator.textContent =
            "data online";

        apiIndicator.className =
            "api-indicator online";

    } catch (error) {
        apiIndicator.textContent =
            "data offline";

        apiIndicator.className =
            "api-indicator offline";
    }
}


async function loadSeasons() {
    const data = await fetchJSON(
        "/api/data/seasons"
    );

    const seasons = [
        ...data.seasons
    ].sort(
        (a, b) =>
            b.season - a.season
    );

    seasonSelect.innerHTML = "";

    for (const season of seasons) {
        const option =
            document.createElement(
                "option"
            );

        option.value =
            season.season;

        option.textContent =
            formatSeason(
                season.season
            );

        seasonSelect.appendChild(
            option
        );
    }

    if (seasons.length === 0) {
        return null;
    }

    seasonSelect.value =
        seasons[0].season;

    return seasons[0].season;
}


async function loadFixtures(season) {
    matchesContainer.innerHTML = `
        <div class="loading-card">
            Loading matches...
        </div>
    `;

    matchSummary.textContent =
        "Loading matches...";

    try {
        const data = await fetchJSON(
            `/api/fixtures?season=${season}&limit=500`
        );

        renderFixtures(
            data.fixtures
        );

        matchSummary.textContent =
            `${data.count} matches in ${formatSeason(
                Number(season)
            )}`;

        sidebarMatchCount.textContent =
            data.count;

    } catch (error) {
        console.error(
            error
        );

        matchesContainer.innerHTML = `
            <div class="error-card">
                Could not load matches.
            </div>
        `;

        matchSummary.textContent =
            "Could not load match data";
    }
}


async function fetchStandings(season) {
    return fetchJSON(
        `/api/standings?season=${season}`
    );
}


async function loadStandings(season) {
    standingsBody.innerHTML = `
        <tr>
            <td
                colspan="10"
                class="standings-message"
            >
                Loading standings...
            </td>
        </tr>
    `;

    standingsSummary.textContent =
        "Loading standings...";

    try {
        const data = await fetchStandings(
            season
        );

        renderStandings(
            data.standings,
            Number(season)
        );

        standingsSummary.textContent =
            `${data.count} teams in ${formatSeason(
                Number(season)
            )}`;

    } catch (error) {
        console.error(
            error
        );

        standingsBody.innerHTML = `
            <tr>
                <td
                    colspan="10"
                    class="standings-message"
                >
                    Could not load standings.
                </td>
            </tr>
        `;

        standingsSummary.textContent =
            "Could not load standings";
    }
}


async function loadTeams(season) {
    teamsGrid.innerHTML = `
        <div class="loading-card">
            Loading teams...
        </div>
    `;

    teamsSummary.textContent =
        "Loading teams...";

    try {
        const data = await fetchStandings(
            season
        );

        renderTeams(
            data.standings,
            Number(season)
        );

        teamsSummary.textContent =
            `${data.count} teams in ${formatSeason(
                Number(season)
            )}`;

    } catch (error) {
        console.error(
            error
        );

        teamsGrid.innerHTML = `
            <div class="error-card">
                Could not load teams.
            </div>
        `;

        teamsSummary.textContent =
            "Could not load teams";
    }
}


function setActiveNavigation(view) {
    matchesTab.classList.toggle(
        "active",
        view === "matches"
    );

    standingsTab.classList.toggle(
        "active",
        view === "standings"
    );

    teamsTab.classList.toggle(
        "active",
        view === "teams"
    );

    sidebarMatches.classList.toggle(
        "active",
        view === "matches"
    );

    sidebarStandings.classList.toggle(
        "active",
        view === "standings"
    );

    sidebarTeams.classList.toggle(
        "active",
        view === "teams"
    );
}


function hideAllViews() {
    matchesView.classList.add(
        "hidden"
    );

    standingsView.classList.add(
        "hidden"
    );

    teamsView.classList.add(
        "hidden"
    );
}


async function showMatches() {
    activeView =
        "matches";

    hideAllViews();

    matchesView.classList.remove(
        "hidden"
    );

    setActiveNavigation(
        "matches"
    );

    await loadFixtures(
        seasonSelect.value
    );
}


async function showStandings() {
    activeView =
        "standings";

    hideAllViews();

    standingsView.classList.remove(
        "hidden"
    );

    setActiveNavigation(
        "standings"
    );

    await loadStandings(
        seasonSelect.value
    );
}


async function showTeams() {
    activeView =
        "teams";

    hideAllViews();

    teamsView.classList.remove(
        "hidden"
    );

    setActiveNavigation(
        "teams"
    );

    await loadTeams(
        seasonSelect.value
    );
}


async function handleSeasonChange() {
    if (activeView === "standings") {
        await loadStandings(
            seasonSelect.value
        );

        return;
    }

    if (activeView === "teams") {
        await loadTeams(
            seasonSelect.value
        );

        return;
    }

    await loadFixtures(
        seasonSelect.value
    );
}


async function loadPage() {
    await loadHealth();

    try {
        const season =
            await loadSeasons();

        if (season !== null) {
            await loadFixtures(
                season
            );
        }

    } catch (error) {
        console.error(
            error
        );

        matchesContainer.innerHTML = `
            <div class="error-card">
                Could not load Premier League data.
            </div>
        `;
    }
}


matchesTab.addEventListener(
    "click",
    showMatches
);

standingsTab.addEventListener(
    "click",
    showStandings
);

teamsTab.addEventListener(
    "click",
    showTeams
);

sidebarMatches.addEventListener(
    "click",
    showMatches
);

sidebarStandings.addEventListener(
    "click",
    showStandings
);

sidebarTeams.addEventListener(
    "click",
    showTeams
);

seasonSelect.addEventListener(
    "change",
    handleSeasonChange
);


loadPage();