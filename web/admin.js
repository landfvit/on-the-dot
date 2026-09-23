const overviewCards = document.getElementById(
    "overview-cards"
);

const seasonTable = document.getElementById(
    "season-table"
);

const qualityGrid = document.getElementById(
    "quality-grid"
);

const importsTable = document.getElementById(
    "imports-table"
);

const fixturesTable = document.getElementById(
    "fixtures-table"
);

const teamsGrid = document.getElementById(
    "teams-grid"
);

const seasonFilter = document.getElementById(
    "season-filter"
);

const teamFilter = document.getElementById(
    "team-filter"
);

const dataStatusFilter = document.getElementById(
    "data-status-filter"
);

const limitFilter = document.getElementById(
    "limit-filter"
);

const resetFiltersButton = document.getElementById(
    "reset-filters"
);

const fixtureCount = document.getElementById(
    "fixture-count"
);

const apiStatus = document.getElementById(
    "api-status"
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


function formatDate(value) {
    if (!value) {
        return "";
    }

    const date = new Date(
        value
    );

    return date.toLocaleString();
}


function formatSeason(season) {
    return `${season}/${String(
        season + 1
    ).slice(-2)}`;
}


async function loadHealth() {
    try {
        const data = await fetchJSON(
            "/api/health"
        );

        apiStatus.textContent = data.status;

        apiStatus.className =
            "api-status ok";

    } catch (error) {
        apiStatus.textContent =
            "offline";

        apiStatus.className =
            "api-status error";
    }
}


async function loadSeasons() {
    const data = await fetchJSON(
        "/api/data/seasons"
    );

    seasonTable.innerHTML = "";

    let totalFixtures = 0;
    let totalCompleteStats = 0;
    let totalMissingStats = 0;

    for (const season of data.seasons) {
        totalFixtures +=
            season.total_fixtures;

        totalCompleteStats +=
            season.fixtures_with_complete_stats;

        totalMissingStats +=
            season.fixtures_without_stats;

        const row = document.createElement(
            "tr"
        );

        row.innerHTML = `
            <td>
                ${formatSeason(season.season)}
            </td>

            <td>
                ${season.teams}
            </td>

            <td>
                ${season.total_fixtures}
            </td>

            <td>
                ${season.finished_fixtures}
            </td>

            <td>
                ${season.fixtures_with_complete_stats}
            </td>

            <td>
                ${season.fixtures_without_stats}
            </td>

            <td>
                ${season.statistics_coverage_percentage}%
            </td>
        `;

        seasonTable.appendChild(
            row
        );
    }


    overviewCards.innerHTML = `
        <div class="card">
            <div class="card-label">
                Seasons
            </div>

            <div class="card-value">
                ${data.count}
            </div>
        </div>


        <div class="card">
            <div class="card-label">
                Fixtures
            </div>

            <div class="card-value">
                ${totalFixtures}
            </div>
        </div>


        <div class="card">
            <div class="card-label">
                Complete statistics
            </div>

            <div class="card-value">
                ${totalCompleteStats}
            </div>
        </div>


        <div class="card">
            <div class="card-label">
                Missing statistics
            </div>

            <div class="card-value">
                ${totalMissingStats}
            </div>
        </div>
    `;


    seasonFilter.innerHTML = `
        <option value="">
            All seasons
        </option>
    `;

    for (const season of data.seasons) {
        const option = document.createElement(
            "option"
        );

        option.value =
            season.season;

        option.textContent =
            formatSeason(
                season.season
            );

        seasonFilter.appendChild(
            option
        );
    }
}


async function loadQuality() {
    const data = await fetchJSON(
        "/api/data/quality"
    );

    qualityGrid.innerHTML = "";

    for (const check of data.checks) {
        const item = document.createElement(
            "div"
        );

        item.className =
            "quality-item";

        const statusClass = (
            check.issues === 0
                ? "status-ok"
                : "status-issue"
        );

        const statusText = (
            check.issues === 0
                ? "OK"
                : `${check.issues} issues`
        );

        const name = check.name
            .replaceAll(
                "_",
                " "
            );

        item.innerHTML = `
            <span class="quality-name">
                ${name}
            </span>

            <span class="${statusClass}">
                ${statusText}
            </span>
        `;

        qualityGrid.appendChild(
            item
        );
    }
}


async function loadImports() {
    const data = await fetchJSON(
        "/api/data/imports?limit=10"
    );

    importsTable.innerHTML = "";

    for (const importRun of data.imports) {
        const row = document.createElement(
            "tr"
        );

        let statusClass = "";

        if (
            importRun.status ===
            "success"
        ) {
            statusClass =
                "import-success";
        }

        if (
            importRun.status ===
            "partial"
        ) {
            statusClass =
                "import-partial";
        }

        if (
            importRun.status ===
            "failed"
        ) {
            statusClass =
                "import-failed";
        }

        row.innerHTML = `
            <td>
                ${importRun.import_type}
            </td>

            <td>
                ${
                    importRun.season
                        ? formatSeason(
                            importRun.season
                        )
                        : ""
                }
            </td>

            <td class="${statusClass}">
                ${importRun.status}
            </td>

            <td>
                ${importRun.rows_inserted}
            </td>

            <td>
                ${importRun.api_requests}
            </td>

            <td>
                ${formatDate(
                    importRun.started_at
                )}
            </td>
        `;

        importsTable.appendChild(
            row
        );
    }
}


async function loadTeams() {
    const data = await fetchJSON(
        "/api/teams"
    );

    teamsGrid.innerHTML = "";

    teamFilter.innerHTML = `
        <option value="">
            All teams
        </option>
    `;

    for (const team of data.teams) {
        const option = document.createElement(
            "option"
        );

        option.value =
            team.team_name;

        option.textContent =
            team.team_name;

        teamFilter.appendChild(
            option
        );


        const card = document.createElement(
            "div"
        );

        card.className =
            "team-card";

        card.innerHTML = `
            <div class="team-name">
                ${team.team_name}
            </div>

            <div class="team-fixtures">
                ${team.fixtures} fixtures
            </div>
        `;

        teamsGrid.appendChild(
            card
        );
    }
}


async function loadFixtures() {
    const params = new URLSearchParams();

    params.set(
        "limit",
        limitFilter.value
    );

    if (seasonFilter.value) {
        params.set(
            "season",
            seasonFilter.value
        );
    }

    if (teamFilter.value) {
        params.set(
            "team",
            teamFilter.value
        );
    }

    if (dataStatusFilter.value) {
        params.set(
            "data_status",
            dataStatusFilter.value
        );
    }

    const url = (
        `/api/fixtures?${params.toString()}`
    );

    const data = await fetchJSON(
        url
    );

    fixturesTable.innerHTML = "";

    fixtureCount.textContent =
        `${data.count} fixtures shown`;


    for (const fixture of data.fixtures) {
        const row = document.createElement(
            "tr"
        );

        let dataClass = "";

        if (
            fixture.data_status ===
            "complete"
        ) {
            dataClass =
                "status-complete";
        }

        if (
            fixture.data_status ===
            "partial"
        ) {
            dataClass =
                "status-partial";
        }

        if (
            fixture.data_status ===
            "missing"
        ) {
            dataClass =
                "status-missing";
        }

        const score = (
            fixture.home_goals !== null
            && fixture.away_goals !== null
        )
            ? (
                `${fixture.home_goals}`
                + " - "
                + `${fixture.away_goals}`
            )
            : "-";

        row.innerHTML = `
            <td>
                ${formatDate(
                    fixture.match_date
                )}
            </td>

            <td>
                ${formatSeason(
                    fixture.season
                )}
            </td>

            <td>
                ${fixture.home_team}
            </td>

            <td>
                ${score}
            </td>

            <td>
                ${fixture.away_team}
            </td>

            <td class="${dataClass}">
                ${fixture.data_status}
            </td>
        `;

        fixturesTable.appendChild(
            row
        );
    }
}


function resetFilters() {
    seasonFilter.value = "";
    teamFilter.value = "";
    dataStatusFilter.value = "";
    limitFilter.value = "30";

    loadFixtures();
}


async function loadDashboard() {
    try {
        await loadHealth();

        await Promise.all(
            [
                loadSeasons(),
                loadQuality(),
                loadImports(),
                loadTeams()
            ]
        );

        await loadFixtures();

    } catch (error) {
        console.error(
            error
        );

        overviewCards.innerHTML = `
            <div class="error-message">
                Could not load dashboard data.
            </div>
        `;
    }
}


seasonFilter.addEventListener(
    "change",
    loadFixtures
);

teamFilter.addEventListener(
    "change",
    loadFixtures
);

dataStatusFilter.addEventListener(
    "change",
    loadFixtures
);

limitFilter.addEventListener(
    "change",
    loadFixtures
);

resetFiltersButton.addEventListener(
    "click",
    resetFilters
);


loadDashboard();