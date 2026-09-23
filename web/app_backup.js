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


function createMatchRow(fixture) {
    const row = document.createElement(
        "div"
    );

    row.className =
        "match-row";

    const score = getScore(
        fixture
    );

    const dataStatus = (
        fixture.data_status
        || "missing"
    );

    row.innerHTML = `
        <div class="match-status">
            ${getMatchStatus(fixture)}
        </div>

        <div class="team home">
            ${fixture.home_team}
        </div>

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

        <div class="team away">
            ${fixture.away_team}
        </div>

        <div class="data-status ${dataStatus}">
            ${dataStatus}
        </div>
    `;

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

    const groupedFixtures =
        groupFixturesByDate(
            fixtures
        );

    for (
        const fixturesForDay
        of groupedFixtures.values()
    ) {
        const matchDay = document.createElement(
            "div"
        );

        matchDay.className =
            "match-day";

        const header = document.createElement(
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
        const option = document.createElement(
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


seasonSelect.addEventListener(
    "change",
    () => {
        loadFixtures(
            seasonSelect.value
        );
    }
);


loadPage();