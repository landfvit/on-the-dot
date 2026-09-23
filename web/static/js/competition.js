const competitionPage =
    document.getElementById(
        "competition-page"
    );


const leagueId = Number(
    competitionPage.dataset.leagueId
);


const requestedSeason =
    competitionPage.dataset.season
        ? Number(
            competitionPage.dataset.season
        )
        : null;


const competitionName =
    document.getElementById(
        "competition-name"
    );

const competitionCountry =
    document.getElementById(
        "competition-country"
    );

const competitionBadge =
    document.getElementById(
        "competition-badge"
    );

const seasonSelect =
    document.getElementById(
        "competition-season-select"
    );


const tabs = [
    ...document.querySelectorAll(
        ".competition-tab"
    )
];


const views = {
    matches:
        document.getElementById(
            "competition-matches-view"
        ),

    standings:
        document.getElementById(
            "competition-standings-view"
        ),

    teams:
        document.getElementById(
            "competition-teams-view"
        ),

    leaders:
        document.getElementById(
            "competition-leaders-view"
        )
};


const matchesContainer =
    document.getElementById(
        "competition-matches"
    );

const matchesSummary =
    document.getElementById(
        "competition-matches-summary"
    );


const standingsBody =
    document.getElementById(
        "competition-standings-body"
    );

const standingsSummary =
    document.getElementById(
        "competition-standings-summary"
    );


const teamsContainer =
    document.getElementById(
        "competition-teams"
    );

const teamsSummary =
    document.getElementById(
        "competition-teams-summary"
    );


const leadersSummary =
    document.getElementById(
        "competition-leaders-summary"
    );

const leadersHead =
    document.getElementById(
        "competition-leaders-head"
    );

const leadersBody =
    document.getElementById(
        "competition-leaders-body"
    );

const leaderTabs = [
    ...document.querySelectorAll(
        ".competition-leader-tab"
    )
];


let activeView = "matches";
let activeLeaderType = "scorers";

let currentSeason = null;

const calendar = document.querySelector(".fixture-calendar");
const calendarDays = document.getElementById("calendar-days");
const calendarMonthLabel = document.getElementById("calendar-month");
const previousMonth = document.getElementById("calendar-previous");
const nextMonth = document.getElementById("calendar-next");
let seasonFixtures = [];
let fixturesSeason = null;
let selectedDay = null;
let calendarMonth = null;
let matchesRequest = 0;

function selectFixtureDay(day) {
    selectedDay = day;
    const date = FixtureCalendar.parseDay(day);
    calendarMonth = new Date(date.getFullYear(), date.getMonth(), 1, 12);
    renderCalendar();
    const matches = seasonFixtures.filter(f => FixtureCalendar.dateKey(f.match_date) === day);
    renderMatches(matches);
    matchesSummary.textContent = `${formatMatchDate(date)} · ${matches.length} ${matches.length === 1 ? "match" : "matches"}`;
    const url = new URL(window.location.href);
    url.searchParams.set("date", day);
    window.history.replaceState({}, "", url);
}

function renderCalendar() {
    const counts = new Map();
    for (const fixture of seasonFixtures) {
        const key = FixtureCalendar.dateKey(fixture.match_date);
        counts.set(key, (counts.get(key) || 0) + 1);
    }
    calendarMonthLabel.textContent = calendarMonth.toLocaleDateString("en-GB", {month: "long", year: "numeric"});
    const first = new Date(seasonFixtures[0].match_date);
    const last = new Date(seasonFixtures.at(-1).match_date);
    const monthIndex = date => date.getFullYear() * 12 + date.getMonth();
    previousMonth.disabled = monthIndex(calendarMonth) <= monthIndex(first);
    nextMonth.disabled = monthIndex(calendarMonth) >= monthIndex(last);
    calendarDays.replaceChildren();
    for (const date of FixtureCalendar.monthDays(calendarMonth)) {
        const key = FixtureCalendar.dateKey(date);
        const count = counts.get(key) || 0;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "calendar-day";
        button.classList.toggle("outside-month", date.getMonth() !== calendarMonth.getMonth());
        button.classList.toggle("has-fixtures", count > 0);
        button.classList.toggle("selected", key === selectedDay);
        button.setAttribute("aria-pressed", String(key === selectedDay));
        button.setAttribute("aria-label", `${formatMatchDate(date)}, ${count} ${count === 1 ? "match" : "matches"}`);
        if (key === FixtureCalendar.dateKey(new Date())) button.setAttribute("aria-current", "date");
        const number = document.createElement("span");
        number.textContent = date.getDate();
        const marker = document.createElement("small");
        marker.textContent = count || "";
        button.append(number, marker);
        button.addEventListener("click", () => {
            selectFixtureDay(key);
            calendarDays.querySelector('[aria-pressed="true"]')?.focus({preventScroll: true});
        });
        calendarDays.appendChild(button);
    }
}

for (const [button, step] of [[previousMonth, -1], [nextMonth, 1]]) {
    button.addEventListener("click", () => {
        calendarMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + step, 1, 12);
        renderCalendar();
    });
}
document.getElementById("calendar-today").addEventListener("click", () =>
    selectFixtureDay(FixtureCalendar.dateKey(new Date())));
document.getElementById("calendar-nearest").addEventListener("click", () =>
    selectFixtureDay(FixtureCalendar.defaultDay(seasonFixtures)));


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


function getInitials(name) {
    const words =
        name.trim().split(
            /\s+/
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


function createLogoImage(
    logoUrl,
    alt,
    className
) {
    const image =
        document.createElement(
            "img"
        );

    image.src =
        logoUrl;

    image.alt =
        alt;

    image.loading =
        "lazy";

    image.className =
        className;

    image.addEventListener(
        "error",
        () => {
            image.remove();
        }
    );

    return image;
}


function renderLogoBadge(
    container,
    logoUrl,
    alt,
    fallback,
    className
) {
    container.innerHTML =
        "";

    if (logoUrl) {
        container.appendChild(
            createLogoImage(
                logoUrl,
                alt,
                className
            )
        );

        return;
    }

    container.textContent =
        fallback;
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
    return new Date(
        value
    ).toLocaleDateString(
        "en-CA"
    );
}


function getMatchStatus(fixture) {
    if (fixture.status !== "NS" && fixture.status !== "TBD") {
        return fixture.status;
    }


    return new Date(
        fixture.match_date
    ).toLocaleTimeString(
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


function createTeamLink(
    teamId,
    teamName,
    season,
    className = "",
    logoUrl = null
) {
    const link =
        document.createElement(
            "a"
        );


    link.href =
        `/teams/${teamId}?season=${season}`;


    link.className =
        `entity-trigger ${className}`.trim();


    link.dataset.entityType =
        "team";


    link.dataset.entityId =
        teamId;


    link.dataset.season =
        season;

    if (logoUrl) {
        link.appendChild(
            createLogoImage(
                logoUrl,
                teamName,
                "competition-team-logo"
            )
        );
    }

    const label =
        document.createElement(
            "span"
        );

    label.textContent =
        teamName;

    link.appendChild(
        label
    );


    return link;
}


function groupFixturesByDate(fixtures) {
    const groups =
        new Map();


    for (
        const fixture
        of fixtures
    ) {
        const key =
            getDateKey(
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
    const row =
        document.createElement(
            "div"
        );


    row.className =
        "competition-match-row";


    row.setAttribute(
        "role",
        "link"
    );


    row.setAttribute(
        "tabindex",
        "0"
    );


    const score =
        getScore(
            fixture
        );


    const status =
        document.createElement(
            "div"
        );


    status.className =
        "competition-match-status";


    status.textContent =
        getMatchStatus(
            fixture
        );


    const home =
        document.createElement(
            "div"
        );


    home.className =
        "competition-match-team home";


    home.appendChild(
        createTeamLink(
            fixture.home_team_id,
            fixture.home_team,
            fixture.season,
            "competition-team-link",
            fixture.home_team_logo_url
        )
    );


    const scoreElement =
        document.createElement(
            "div"
        );


    scoreElement.className =
        "competition-match-score";


    scoreElement.innerHTML = `
        <span>
            ${score.home}
        </span>

        <span>
            -
        </span>

        <span>
            ${score.away}
        </span>
    `;


    const away =
        document.createElement(
            "div"
        );


    away.className =
        "competition-match-team away";


    away.appendChild(
        createTeamLink(
            fixture.away_team_id,
            fixture.away_team,
            fixture.season,
            "competition-team-link",
            fixture.away_team_logo_url
        )
    );


    const dataStatus =
        document.createElement(
            "div"
        );


    dataStatus.className =
        `competition-data-status ${fixture.data_status || "missing"}`;


    dataStatus.textContent =
        fixture.data_status
        || "missing";


    row.appendChild(
        status
    );


    row.appendChild(
        home
    );


    row.appendChild(
        scoreElement
    );


    row.appendChild(
        away
    );


    row.appendChild(
        dataStatus
    );


    function openMatch() {
        window.location.href =
            `/matches/${fixture.fixture_id}`;
    }


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


            openMatch();
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

                openMatch();
            }
        }
    );


    return row;
}


function renderMatches(fixtures) {
    matchesContainer.innerHTML =
        "";


    if (
        fixtures.length === 0
    ) {
        matchesContainer.innerHTML = `
            <div class="competition-empty">
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
        const group =
            document.createElement(
                "section"
            );


        group.className =
            "competition-match-day";


        const header =
            document.createElement(
                "div"
            );


        header.className =
            "competition-match-day-header";


        header.textContent =
            formatMatchDate(
                fixturesForDay[0].match_date
            );


        group.appendChild(
            header
        );


        for (
            const fixture
            of fixturesForDay
        ) {
            group.appendChild(
                createMatchRow(
                    fixture
                )
            );
        }


        matchesContainer.appendChild(
            group
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


function renderStandings(standings) {
    standingsBody.innerHTML =
        "";


    if (
        standings.length === 0
    ) {
        standingsBody.innerHTML = `
            <tr>

                <td
                    colspan="10"
                    class="competition-empty"
                >
                    No standings found.
                </td>

            </tr>
        `;

        return;
    }


    for (
        const team
        of standings
    ) {
        const row =
            document.createElement(
                "tr"
            );


        const teamCell =
            document.createElement(
                "td"
            );


        teamCell.appendChild(
            createTeamLink(
                team.team_id,
                team.team_name,
                currentSeason,
                "competition-standings-team-link",
                team.team_logo_url
            )
        );


        row.innerHTML = `
            <td class="competition-standings-position">
                ${team.position}
            </td>
        `;


        row.appendChild(
            teamCell
        );


        const values = [
            team.played,
            team.wins,
            team.draws,
            team.losses,
            team.goals_for,
            team.goals_against,
            formatGoalDifference(
                team.goal_difference
            )
        ];


        for (
            const value
            of values
        ) {
            const cell =
                document.createElement(
                    "td"
                );


            cell.textContent =
                value;


            row.appendChild(
                cell
            );
        }


        const points =
            document.createElement(
                "td"
            );


        points.className =
            "competition-standings-points";


        points.textContent =
            team.points;


        row.appendChild(
            points
        );


        standingsBody.appendChild(
            row
        );
    }
}


function renderTeams(standings) {
    teamsContainer.innerHTML =
        "";


    if (
        standings.length === 0
    ) {
        teamsContainer.innerHTML = `
            <div class="competition-empty">
                No teams found.
            </div>
        `;

        return;
    }


    for (
        const team
        of standings
    ) {
        const card =
            createTeamLink(
                team.team_id,
                team.team_name,
                currentSeason,
                "competition-team-card"
            );


        card.innerHTML = `
            <div class="competition-team-card-badge">
                ${getInitials(
                    team.team_name
                )}
            </div>

            <div class="competition-team-card-content">

                <h3 class="competition-team-card-name">
                    ${team.team_name}
                </h3>

                <div class="competition-team-card-meta">
                    ${team.points} pts
                    ·
                    ${formatGoalDifference(
                        team.goal_difference
                    )} GD
                </div>

            </div>

            <div class="competition-team-card-position">
                #${team.position}
            </div>
        `;

        renderLogoBadge(
            card.querySelector(
                ".competition-team-card-badge"
            ),
            team.team_logo_url,
            team.team_name,
            getInitials(
                team.team_name
            ),
            "competition-team-card-logo"
        );


        teamsContainer.appendChild(
            card
        );
    }
}


async function loadMatches() {
    if (fixturesSeason === currentSeason && seasonFixtures.length) {
        selectFixtureDay(selectedDay);
        return;
    }
    const request = ++matchesRequest;
    const season = currentSeason;
    calendar.hidden = true;
    matchesContainer.innerHTML = `
        <div class="competition-loading">
            Loading matches...
        </div>
    `;


    matchesSummary.textContent =
        "Loading matches...";


    try {
        const data =
            await fetchJSON(
                `/api/fixtures?league_id=${leagueId}&season=${season}&limit=500`
            );


        if (request !== matchesRequest || season !== currentSeason) return;
        seasonFixtures = FixtureCalendar.sortFixtures(data.fixtures);
        fixturesSeason = season;
        if (!seasonFixtures.length) {
            renderMatches([]);
            matchesSummary.textContent = `No matches in ${formatSeason(season)}`;
            return;
        }
        const requestedDay = new URL(window.location.href).searchParams.get("date");
        const validDay = FixtureCalendar.parseDay(requestedDay);
        const firstDay = FixtureCalendar.dateKey(seasonFixtures[0].match_date);
        const lastDay = FixtureCalendar.dateKey(seasonFixtures.at(-1).match_date);
        const day = validDay && requestedDay >= firstDay && requestedDay <= lastDay
            ? requestedDay : FixtureCalendar.defaultDay(seasonFixtures);
        calendar.hidden = false;
        selectFixtureDay(day);

    } catch (error) {
        if (request !== matchesRequest || season !== currentSeason) return;
        console.error(
            error
        );


        matchesContainer.innerHTML = `
            <div class="competition-error">
                Could not load matches.
            </div>
        `;


        matchesSummary.textContent =
            "Could not load matches";
    }
}


async function loadStandings() {
    standingsBody.innerHTML = `
        <tr>

            <td
                colspan="10"
                class="competition-loading"
            >
                Loading standings...
            </td>

        </tr>
    `;


    try {
        const data =
            await fetchJSON(
                `/api/standings?league_id=${leagueId}&season=${currentSeason}`
            );


        renderStandings(
            data.standings
        );


        standingsSummary.textContent =
            `${data.count} teams in ${formatSeason(
                currentSeason
            )}`;

    } catch (error) {
        console.error(
            error
        );


        standingsBody.innerHTML = `
            <tr>

                <td
                    colspan="10"
                    class="competition-error"
                >
                    Could not load standings.
                </td>

            </tr>
        `;
    }
}


async function loadTeams() {
    teamsContainer.innerHTML = `
        <div class="competition-loading">
            Loading teams...
        </div>
    `;


    try {
        const data =
            await fetchJSON(
                `/api/standings?league_id=${leagueId}&season=${currentSeason}`
            );


        renderTeams(
            data.standings
        );


        teamsSummary.textContent =
            `${data.count} teams in ${formatSeason(
                currentSeason
            )}`;

    } catch (error) {
        console.error(
            error
        );


        teamsContainer.innerHTML = `
            <div class="competition-error">
                Could not load teams.
            </div>
        `;
    }
}


function formatLeaderRating(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    return Number(
        value
    ).toFixed(
        2
    );
}


function createLeaderPlayerCell(
    leader
) {
    const cell =
        document.createElement(
            "td"
        );

    const link =
        document.createElement(
            "a"
        );

    link.href =
        `/players/${leader.player_id}?season=${currentSeason}`;

    link.className =
        "competition-leader-player entity-trigger";

    link.dataset.entityType =
        "player";

    link.dataset.entityId =
        leader.player_id;

    link.dataset.season =
        currentSeason;

    if (leader.photo_url) {
        const image =
            document.createElement(
                "img"
            );

        image.src =
            leader.photo_url;

        image.alt =
            leader.player_name;

        image.loading =
            "lazy";

        image.className =
            "competition-leader-photo";

        image.addEventListener(
            "error",
            () => {
                image.remove();
            }
        );

        link.appendChild(
            image
        );
    }

    const text =
        document.createElement(
            "span"
        );

    text.className =
        "competition-leader-player-text";

    text.innerHTML = `
        <strong>${leader.player_name}</strong>
        <small>${leader.teams || "-"}</small>
    `;

    link.appendChild(
        text
    );

    cell.appendChild(
        link
    );

    return cell;
}


function renderLeaders(
    leaders,
    leaderType
) {
    leadersHead.innerHTML = "";
    leadersBody.innerHTML = "";

    let columns;

    if (leaderType === "rating") {
        columns = [
            "#",
            "Player",
            "Rating",
            "Apps",
            "Min"
        ];

    } else if (
        leaderType === "goalkeepers"
    ) {
        columns = [
            "#",
            "Goalkeeper",
            "Saves",
            "GC",
            "Saves/90",
            "Rating"
        ];

    } else {
        columns = [
            "#",
            "Player",
            "G",
            "A",
            "G+A"
        ];
    }

    const headRow =
        document.createElement(
            "tr"
        );

    for (const column of columns) {
        const th =
            document.createElement(
                "th"
            );

        th.textContent =
            column;

        headRow.appendChild(
            th
        );
    }

    leadersHead.appendChild(
        headRow
    );

    if (!leaders.length) {
        const row =
            document.createElement(
                "tr"
            );

        row.innerHTML = `
            <td
                colspan="${columns.length}"
                class="competition-empty"
            >
                No leaderboard data available.
            </td>
        `;

        leadersBody.appendChild(
            row
        );

        return;
    }

    for (const leader of leaders) {
        const row =
            document.createElement(
                "tr"
            );

        const rank =
            document.createElement(
                "td"
            );

        rank.className =
            "competition-leader-rank";

        rank.textContent =
            leader.rank;

        row.appendChild(
            rank
        );

        row.appendChild(
            createLeaderPlayerCell(
                leader
            )
        );

        let values;

        if (leaderType === "rating") {
            values = [
                formatLeaderRating(
                    leader.provider_rating
                ),
                leader.appearances ?? 0,
                leader.minutes ?? 0
            ];

        } else if (
            leaderType === "goalkeepers"
        ) {
            values = [
                leader.saves ?? 0,
                leader.goals_conceded ?? 0,
                leader.saves_per_90 ?? "-",
                formatLeaderRating(
                    leader.provider_rating
                )
            ];

        } else {
            values = [
                leader.goals ?? 0,
                leader.assists ?? 0,
                leader.goal_contributions ?? 0
            ];
        }

        for (const value of values) {
            const cell =
                document.createElement(
                    "td"
                );

            cell.textContent =
                value;

            row.appendChild(
                cell
            );
        }

        leadersBody.appendChild(
            row
        );
    }
}


async function loadLeaders() {
    leadersBody.innerHTML = `
        <tr>
            <td
                colspan="6"
                class="competition-loading"
            >
                Loading leaders...
            </td>
        </tr>
    `;

    leadersSummary.textContent =
        "Loading season leaders...";

    try {
        const params =
            new URLSearchParams(
                {
                    season: currentSeason,
                    type: activeLeaderType,
                    limit: 20
                }
            );

        if (
            activeLeaderType === "rating"
        ) {
            params.set(
                "min_minutes",
                600
            );
        }

        const data =
            await fetchJSON(
                `/api/competitions/${leagueId}/leaders?${params.toString()}`
            );

        renderLeaders(
            data.leaders || [],
            activeLeaderType
        );

        if (
            activeLeaderType === "rating"
        ) {
            leadersSummary.textContent =
                `Provider rating · minimum ${data.min_minutes} minutes · ${formatSeason(currentSeason)}`;

        } else if (
            activeLeaderType === "goalkeepers"
        ) {
            leadersSummary.textContent =
                `Goalkeeper leaders · ${formatSeason(currentSeason)}`;

        } else {
            leadersSummary.textContent =
                `Goals, assists and goal contributions · ${formatSeason(currentSeason)}`;
        }

    } catch (error) {
        console.error(
            error
        );

        leadersBody.innerHTML = `
            <tr>
                <td
                    colspan="6"
                    class="competition-error"
                >
                    Could not load leaders.
                </td>
            </tr>
        `;

        leadersSummary.textContent =
            "Could not load season leaders";
    }
}


async function loadActiveView() {
    if (
        activeView === "standings"
    ) {
        await loadStandings();

        return;
    }


    if (
        activeView === "teams"
    ) {
        await loadTeams();

        return;
    }


    if (
        activeView === "leaders"
    ) {
        await loadLeaders();

        return;
    }


    await loadMatches();
}


function setActiveView(viewName) {
    activeView =
        viewName;


    for (
        const tab
        of tabs
    ) {
        tab.classList.toggle(
            "active",
            tab.dataset.view
                === viewName
        );
    }


    for (
        const [
            name,
            view
        ]
        of Object.entries(
            views
        )
    ) {
        view.classList.toggle(
            "hidden",
            name !== viewName
        );
    }


    loadActiveView();
}


function updateUrl() {
    const url =
        new URL(
            window.location.href
        );


    url.searchParams.set(
        "season",
        currentSeason
    );


    window.history.replaceState(
        {},
        "",
        url
    );
}


async function loadCompetition() {
    try {
        const data =
            await fetchJSON(
                `/api/competitions/${leagueId}`
            );


        competitionName.textContent =
            data.competition.league_name;


        competitionCountry.textContent =
            data.competition.country_name
            || "Competition";


        competitionBadge.textContent =
            getInitials(
                data.competition.league_name
            );

        renderLogoBadge(
            competitionBadge,
            data.competition.logo_url,
            data.competition.league_name,
            getInitials(
                data.competition.league_name
            ),
            "competition-badge-logo"
        );


        document.title =
            `${data.competition.league_name} | PL Analytics`;


        seasonSelect.innerHTML =
            "";


        for (
            const season
            of data.seasons
        ) {
            const option =
                document.createElement(
                    "option"
                );


            option.value =
                season;


            option.textContent =
                formatSeason(
                    season
                );


            seasonSelect.appendChild(
                option
            );
        }


        if (
            data.seasons.length === 0
        ) {
            throw new Error(
                "competition has no seasons"
            );
        }


        if (
            requestedSeason !== null
            && data.seasons.includes(
                requestedSeason
            )
        ) {
            currentSeason =
                requestedSeason;

        } else {
            currentSeason =
                data.seasons[0];
        }


        seasonSelect.value =
            currentSeason;


        updateUrl();


        await loadMatches();

    } catch (error) {
        console.error(
            error
        );


        competitionName.textContent =
            "Could not load competition";
    }
}


for (
    const tab
    of tabs
) {
    tab.addEventListener(
        "click",
        () => {
            setActiveView(
                tab.dataset.view
            );
        }
    );
}


for (
    const tab
    of leaderTabs
) {
    tab.addEventListener(
        "click",
        async () => {
            activeLeaderType =
                tab.dataset.leaderType;

            for (
                const leaderTab
                of leaderTabs
            ) {
                leaderTab.classList.toggle(
                    "active",
                    leaderTab === tab
                );
            }

            await loadLeaders();
        }
    );
}


seasonSelect.addEventListener(
    "change",
    async () => {
        ++matchesRequest;
        fixturesSeason = null;
        selectedDay = null;
        calendar.hidden = true;
        const url = new URL(window.location.href);
        url.searchParams.delete("date");
        window.history.replaceState({}, "", url);
        currentSeason =
            Number(
                seasonSelect.value
            );


        updateUrl();


        await loadActiveView();
    }
);


loadCompetition();
