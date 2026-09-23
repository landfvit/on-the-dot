const matchPage = document.getElementById(
    "match-page"
);

const fixtureId = Number(
    matchPage.dataset.fixtureId
);

const matchDate = document.getElementById(
    "match-date"
);

const matchStatus = document.getElementById(
    "match-status"
);

const matchCompetitionLink = document.getElementById(
    "match-competition-link"
);

const matchCompetitionLogo = document.getElementById(
    "match-competition-logo"
);

const matchCompetitionName = document.getElementById(
    "match-competition-name"
);

const matchBackLink = document.getElementById(
    "match-back-link"
);

const homeTeam = document.getElementById(
    "home-team"
);

const awayTeam = document.getElementById(
    "away-team"
);

const homeTeamLogo = document.getElementById(
    "home-team-logo"
);

const awayTeamLogo = document.getElementById(
    "away-team-logo"
);

const homePosition = document.getElementById(
    "home-position"
);

const awayPosition = document.getElementById(
    "away-position"
);

const homeForm = document.getElementById(
    "home-form"
);

const awayForm = document.getElementById(
    "away-form"
);

const homeScore = document.getElementById(
    "home-score"
);

const awayScore = document.getElementById(
    "away-score"
);

const homeRecentTitle = document.getElementById(
    "home-recent-title"
);

const awayRecentTitle = document.getElementById(
    "away-recent-title"
);

const homeRecentMatches = document.getElementById(
    "home-recent-matches"
);

const awayRecentMatches = document.getElementById(
    "away-recent-matches"
);

const h2hContainer = document.getElementById(
    "h2h-container"
);

const statisticsContainer = document.getElementById(
    "statistics-container"
);

const navigationButtons = document.querySelectorAll(
    ".match-navigation-item[data-view]"
);

const contentViews = document.querySelectorAll(
    ".match-content-view"
);

let brandingData = null;


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


async function loadBranding() {
    if (window.entityBrandingData) {
        brandingData =
            window.entityBrandingData;

        return brandingData;
    }

    try {
        brandingData = await fetchJSON(
            "/api/branding"
        );

        return brandingData;

    } catch (error) {
        console.error(
            "branding could not be loaded:",
            error
        );

        return null;
    }
}


function getTeamBranding(teamId) {
    return (
        brandingData
        ?.sports
        ?.football
        ?.teams
        ?.[String(teamId)]
        || null
    );
}


function getCompetitionBranding(
    leagueId
) {
    return (
        brandingData
        ?.sports
        ?.football
        ?.competitions
        ?.[String(leagueId)]
        || null
    );
}


function formatDate(value) {
    const date = new Date(
        value
    );

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        }
    ).format(
        date
    );
}


function formatShortDate(value) {
    const date = new Date(
        value
    );

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            day: "2-digit",
            month: "short"
        }
    ).format(
        date
    );
}


function formatSeason(season) {
    return `${season}/${String(
        season + 1
    ).slice(-2)}`;
}


function displayValue(
    value,
    suffix = ""
) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    return `${value}${suffix}`;
}


function setupTeamEntity(
    container,
    teamId,
    season,
    teamName
) {
    container.innerHTML =
        "";

    const link =
        document.createElement(
            "a"
        );

    link.href =
        `/teams/${teamId}?season=${season}`;

    link.textContent =
        teamName;

    link.className =
        "entity-trigger match-team-link";

    link.dataset.entityType =
        "team";

    link.dataset.entityId =
        teamId;

    link.dataset.season =
        season;

    container.appendChild(
        link
    );
}


function renderLogo(
    container,
    branding,
    fallback,
    fallbackLogoUrl = null,
    teamName = fallback
) {
    container.innerHTML =
        "";

    const logoUrl =
        branding?.logo_url
        || fallbackLogoUrl;

    if (
        logoUrl
    ) {
        const image =
            document.createElement(
                "img"
            );

        image.src =
            logoUrl;

        image.alt =
            teamName;

        image.loading =
            "eager";

        image.addEventListener(
            "error",
            () => {
                image.remove();

                container.textContent =
                    fallback;
            }
        );

        container.appendChild(
            image
        );

        return;
    }

    container.textContent =
        fallback;
}


function createStatRow(
    name,
    homeValue,
    awayValue,
    suffix = ""
) {
    const row =
        document.createElement(
            "div"
        );

    row.className =
        "stat-row";

    row.innerHTML = `
        <div class="stat-value home">
            ${displayValue(
                homeValue,
                suffix
            )}
        </div>

        <div class="stat-name">
            ${name}
        </div>

        <div class="stat-value away">
            ${displayValue(
                awayValue,
                suffix
            )}
        </div>
    `;

    const values = [homeValue, awayValue].map(value => {
        if (value === null || value === undefined || value === "") return null;
        const numeric = Number(String(value).replace(/%$/, ""));
        return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
    });
    const total = values[0] + values[1];
    const hasComparison = values.every(value => value !== null) && total > 0;
    const bar = document.createElement("div");
    bar.className = "stat-comparison-bar";
    bar.setAttribute("aria-hidden", "true");

    for (const [index, side] of ["home", "away"].entries()) {
        const segment = document.createElement("span");
        segment.className = `stat-bar-segment ${side}`;
        segment.style.width = `${hasComparison ? values[index] / total * 100 : 0}%`;
        bar.appendChild(segment);
    }
    row.appendChild(bar);

    return row;
}


function renderStatistics(
    statistics
) {
    statisticsContainer.innerHTML =
        "";

    if (
        !Array.isArray(
            statistics
        )
        || statistics.length < 2
    ) {
        statisticsContainer.innerHTML = `
            <div class="no-statistics">
                Detailed statistics are not available for this match.
            </div>
        `;

        return;
    }

    const home =
        statistics[0];

    const away =
        statistics[1];

    const rows = [
        [
            "Ball possession",
            home.ball_possession,
            away.ball_possession,
            "%"
        ],
        [
            "Total shots",
            home.total_shots,
            away.total_shots
        ],
        [
            "Shots on goal",
            home.shots_on_goal,
            away.shots_on_goal
        ],
        [
            "Shots off goal",
            home.shots_off_goal,
            away.shots_off_goal
        ],
        [
            "Blocked shots",
            home.blocked_shots,
            away.blocked_shots
        ],
        [
            "Shots inside box",
            home.shots_inside_box,
            away.shots_inside_box
        ],
        [
            "Shots outside box",
            home.shots_outside_box,
            away.shots_outside_box
        ],
        [
            "Corner kicks",
            home.corner_kicks,
            away.corner_kicks
        ],
        [
            "Fouls",
            home.fouls,
            away.fouls
        ],
        [
            "Offsides",
            home.offsides,
            away.offsides
        ],
        [
            "Yellow cards",
            home.yellow_cards,
            away.yellow_cards
        ],
        [
            "Red cards",
            home.red_cards,
            away.red_cards
        ],
        [
            "Goalkeeper saves",
            home.goalkeeper_saves,
            away.goalkeeper_saves
        ],
        [
            "Total passes",
            home.total_passes,
            away.total_passes
        ],
        [
            "Accurate passes",
            home.passes_accurate,
            away.passes_accurate
        ],
        [
            "Pass accuracy",
            home.passes_percentage,
            away.passes_percentage,
            "%"
        ]
    ];

    const groups = [
        ["Shooting", rows.slice(1, 7)],
        ["Possession & passing", [rows[0], ...rows.slice(13)]],
        ["Attacking play", [rows[7], rows[9]]],
        ["Discipline", [rows[8], rows[10], rows[11]]],
        ["Goalkeeping", [rows[12]]],
    ];
    for (const [title, stats] of groups) {
        const section = document.createElement("section");
        section.className = "match-stat-group";
        const heading = document.createElement("h3");
        heading.textContent = title;
        section.appendChild(heading);
        for (const row of stats) {
            section.appendChild(createStatRow(...row));
        }
        statisticsContainer.appendChild(section);
    }
}


function getTeamResult(
    fixture,
    teamId
) {
    const isHome =
        fixture.home_team_id
        === teamId;

    const teamGoals =
        isHome
            ? fixture.home_goals
            : fixture.away_goals;

    const opponentGoals =
        isHome
            ? fixture.away_goals
            : fixture.home_goals;

    if (
        teamGoals === null
        || teamGoals === undefined
        || opponentGoals === null
        || opponentGoals === undefined
    ) {
        return null;
    }

    if (
        teamGoals
        > opponentGoals
    ) {
        return "W";
    }

    if (
        teamGoals
        < opponentGoals
    ) {
        return "L";
    }

    return "D";
}


function getMatchesBeforeFixture(
    fixtures,
    teamId,
    fixtureDate,
    limit = 5
) {
    const cutoff =
        new Date(
            fixtureDate
        ).getTime();

    return fixtures
        .filter(
            fixture => {
                const matchTime =
                    new Date(
                        fixture.match_date
                    ).getTime();

                return (
                    fixture.fixture_id
                        !== fixtureId
                    && fixture.status
                        === "FT"
                    && matchTime
                        < cutoff
                    && (
                        fixture.home_team_id
                            === teamId
                        || fixture.away_team_id
                            === teamId
                    )
                );
            }
        )
        .sort(
            (a, b) => (
                new Date(
                    b.match_date
                )
                - new Date(
                    a.match_date
                )
            )
        )
        .slice(
            0,
            limit
        );
}


function renderForm(
    container,
    matches,
    teamId
) {
    container.innerHTML =
        "";

    if (
        matches.length === 0
    ) {
        container.innerHTML = `
            <span class="form-empty">
                No previous matches
            </span>
        `;

        return;
    }

    const chronological =
        [
            ...matches
        ].reverse();

    for (
        const fixture
        of chronological
    ) {
        const result =
            getTeamResult(
                fixture,
                teamId
            );

        if (!result) {
            continue;
        }

        const badge =
            document.createElement(
                "span"
            );

        badge.className =
            `form-result ${result.toLowerCase()}`;

        badge.textContent =
            result;

        container.appendChild(
            badge
        );
    }
}


function createTeamLink(
    teamId,
    teamName,
    season,
    logoUrl = null
) {
    const link =
        document.createElement(
            "a"
        );

    link.href =
        `/teams/${teamId}?season=${season}`;

    link.className =
        "entity-trigger recent-team-link";

    link.dataset.entityType =
        "team";

    link.dataset.entityId =
        teamId;

    link.dataset.season =
        season;

    const resolvedLogoUrl =
        getTeamBranding(
            teamId
        )?.logo_url
        || logoUrl;

    if (resolvedLogoUrl) {
        const logo =
            document.createElement(
                "img"
            );

        logo.src =
            resolvedLogoUrl;

        logo.alt =
            teamName;

        logo.loading =
            "lazy";

        logo.className =
            "entity-team-logo-inline";

        logo.addEventListener(
            "error",
            () => {
                logo.remove();
            }
        );

        link.appendChild(
            logo
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


function createRecentOpponent(
    teamId,
    teamName,
    logoUrl = null
) {
    const wrapper =
        document.createElement(
            "span"
        );

    wrapper.className =
        "recent-team-link";

    const branding =
        getTeamBranding(
            teamId
        );

    const resolvedLogoUrl =
        branding?.logo_url
        || logoUrl;

    if (
        resolvedLogoUrl
    ) {
        const logo =
            document.createElement(
                "img"
            );

        logo.src =
            resolvedLogoUrl;

        logo.alt =
            teamName;

        logo.loading =
            "lazy";

        logo.className =
            "entity-team-logo-inline";

        wrapper.appendChild(
            logo
        );
    }

    const name =
        document.createElement(
            "span"
        );

    name.textContent =
        teamName;

    wrapper.appendChild(
        name
    );

    return wrapper;
}


function renderRecentMatches(
    container,
    matches,
    teamId,
    season
) {
    container.innerHTML =
        "";

    if (
        matches.length === 0
    ) {
        container.innerHTML = `
            <div class="recent-empty">
                No previous matches available.
            </div>
        `;

        return;
    }

    for (
        const fixture
        of matches
    ) {
        const row =
            document.createElement(
                "div"
            );

        row.className =
            "recent-result-row";

        row.setAttribute(
            "role",
            "link"
        );

        row.setAttribute(
            "tabindex",
            "0"
        );

        row.setAttribute(
            "aria-label",
            `Open match ${fixture.home_team} vs ${fixture.away_team}`
        );

        row.style.cursor =
            "pointer";


        const date =
            document.createElement(
                "span"
            );

        date.className =
            "recent-result-date";

        date.textContent =
            formatShortDate(
                fixture.match_date
            );


        const isHome =
            fixture.home_team_id
            === teamId;

        const opponentId =
            isHome
                ? fixture.away_team_id
                : fixture.home_team_id;

        const opponentName =
            isHome
                ? fixture.away_team
                : fixture.home_team;

        const opponentLogoUrl =
            isHome
                ? fixture.away_team_logo_url
                : fixture.home_team_logo_url;

        const opponent =
            createRecentOpponent(
                opponentId,
                opponentName,
                opponentLogoUrl
            );


        const result =
            getTeamResult(
                fixture,
                teamId
            );


        const resultBadge =
            document.createElement(
                "span"
            );

        resultBadge.className =
            `form-result compact ${result.toLowerCase()}`;

        resultBadge.textContent =
            result;


        const score =
            document.createElement(
                "span"
            );

        score.className =
            "recent-result-score";

        score.textContent =
            `${fixture.home_goals}:${fixture.away_goals}`;


        row.appendChild(
            date
        );

        row.appendChild(
            opponent
        );

        row.appendChild(
            resultBadge
        );

        row.appendChild(
            score
        );


        const openMatch = () => {
            window.location.href =
                `/matches/${fixture.fixture_id}`;
        };


        row.addEventListener(
            "click",
            openMatch
        );


        row.addEventListener(
            "keydown",
            event => {
                if (
                    event.key === "Enter"
                    || event.key === " "
                ) {
                    event.preventDefault();

                    openMatch();
                }
            }
        );


        container.appendChild(
            row
        );
    }
}


function getHeadToHeadMatches(
    fixtures,
    fixture,
    limit = 5
) {
    const cutoff =
        new Date(
            fixture.match_date
        ).getTime();

    const teams =
        new Set(
            [
                fixture.home_team_id,
                fixture.away_team_id
            ]
        );

    return fixtures
        .filter(
            item => {
                const matchTime =
                    new Date(
                        item.match_date
                    ).getTime();

                return (
                    item.fixture_id
                        !== fixture.fixture_id
                    && item.status
                        === "FT"
                    && matchTime
                        < cutoff
                    && teams.has(
                        item.home_team_id
                    )
                    && teams.has(
                        item.away_team_id
                    )
                );
            }
        )
        .sort(
            (a, b) => (
                new Date(
                    b.match_date
                )
                - new Date(
                    a.match_date
                )
            )
        )
        .slice(
            0,
            limit
        );
}


function renderH2H(
    matches,
    season
) {
    h2hContainer.innerHTML =
        "";

    if (
        matches.length === 0
    ) {
        h2hContainer.innerHTML = `
            <div class="recent-empty">
                No previous head-to-head matches are available.
            </div>
        `;

        return;
    }

    for (
        const fixture
        of matches
    ) {
        const row =
            document.createElement(
                "div"
            );

        row.className =
            "h2h-row";

        const date =
            document.createElement(
                "span"
            );

        date.className =
            "h2h-date";

        date.textContent =
            formatShortDate(
                fixture.match_date
            );

        const home =
            createTeamLink(
                fixture.home_team_id,
                fixture.home_team,
                fixture.season
                || season,
                fixture.home_team_logo_url
            );

        home.classList.add(
            "h2h-team",
            "home"
        );

        const score =
            document.createElement(
                "a"
            );

        score.href =
            `/matches/${fixture.fixture_id}`;

        score.className =
            "h2h-score";

        score.textContent =
            `${fixture.home_goals}:${fixture.away_goals}`;

        const away =
            createTeamLink(
                fixture.away_team_id,
                fixture.away_team,
                fixture.season
                || season,
                fixture.away_team_logo_url
            );

        away.classList.add(
            "h2h-team",
            "away"
        );

        row.appendChild(
            date
        );

        row.appendChild(
            home
        );

        row.appendChild(
            score
        );

        row.appendChild(
            away
        );

        h2hContainer.appendChild(
            row
        );
    }
}


function getStandingPosition(
    standings,
    teamId
) {
    const row =
        standings.find(
            item =>
                item.team_id
                === teamId
        );

    return row?.position
        || null;
}


function renderCompetition(
    fixture
) {
    const branding =
        getCompetitionBranding(
            fixture.league_id
        );

    matchCompetitionLink.href =
        `/competitions/${fixture.league_id}?season=${fixture.season}`;

    matchCompetitionName.textContent =
        branding?.name
        || fixture.league_name
        || "Premier League";

    matchCompetitionLogo.innerHTML =
        "";

    const logoUrl =
        branding?.logo_url
        || fixture.league_logo_url;

    if (
        logoUrl
    ) {
        const image =
            document.createElement(
                "img"
            );

        image.src =
            logoUrl;

        image.alt =
            branding?.name
            || fixture.league_name
            || "Competition";

        matchCompetitionLogo.appendChild(
            image
        );
    }

    matchBackLink.href =
        `/competitions/${fixture.league_id}?season=${fixture.season}`;

    matchBackLink.textContent =
        `← Back to ${
            branding?.name
            || fixture.league_name
            || "competition"
        }`;
}


function renderFixture(
    data,
    standings
) {
    const fixture =
        data.fixture;

    setupTeamEntity(
        homeTeam,
        fixture.home_team_id,
        fixture.season,
        fixture.home_team
    );

    setupTeamEntity(
        awayTeam,
        fixture.away_team_id,
        fixture.season,
        fixture.away_team
    );

    renderLogo(
        homeTeamLogo,
        getTeamBranding(
            fixture.home_team_id
        ),
        "H",
        fixture.home_team_logo_url,
        fixture.home_team
    );

    renderLogo(
        awayTeamLogo,
        getTeamBranding(
            fixture.away_team_id
        ),
        "A",
        fixture.away_team_logo_url,
        fixture.away_team
    );

    const homeStanding =
        getStandingPosition(
            standings,
            fixture.home_team_id
        );

    const awayStanding =
        getStandingPosition(
            standings,
            fixture.away_team_id
        );

    homePosition.textContent =
        homeStanding
            ? `Season position #${homeStanding}`
            : "League position unavailable";

    awayPosition.textContent =
        awayStanding
            ? `Season position #${awayStanding}`
            : "League position unavailable";

    homeScore.textContent =
        fixture.home_goals
        ?? "-";

    awayScore.textContent =
        fixture.away_goals
        ?? "-";

    matchStatus.textContent =
        fixture.status;

    matchDate.textContent =
        `${formatDate(
            fixture.match_date
        )} · ${formatSeason(
            fixture.season
        )}`;

    homeRecentTitle.textContent =
        fixture.home_team;

    awayRecentTitle.textContent =
        fixture.away_team;

    renderCompetition(
        fixture
    );

    renderStatistics(
        data.statistics
    );
}


function renderMatchContext(
    fixture,
    seasonFixtures,
    historyFixtures
) {
    const homeMatches =
        getMatchesBeforeFixture(
            seasonFixtures,
            fixture.home_team_id,
            fixture.match_date,
            5
        );

    const awayMatches =
        getMatchesBeforeFixture(
            seasonFixtures,
            fixture.away_team_id,
            fixture.match_date,
            5
        );

    renderForm(
        homeForm,
        homeMatches,
        fixture.home_team_id
    );

    renderForm(
        awayForm,
        awayMatches,
        fixture.away_team_id
    );

    renderRecentMatches(
        homeRecentMatches,
        homeMatches,
        fixture.home_team_id,
        fixture.season
    );

    renderRecentMatches(
        awayRecentMatches,
        awayMatches,
        fixture.away_team_id,
        fixture.season
    );

    const h2h =
        getHeadToHeadMatches(
            historyFixtures,
            fixture,
            5
        );

    renderH2H(
        h2h,
        fixture.season
    );
}


function showView(
    viewName
) {
    for (
        const button
        of navigationButtons
    ) {
        button.classList.toggle(
            "active",
            button.dataset.view
            === viewName
        );
    }

    for (
        const view
        of contentViews
    ) {
        view.classList.toggle(
            "hidden",
            view.dataset.view
            !== viewName
        );
    }
}


function setupNavigation() {
    for (
        const button
        of navigationButtons
    ) {
        button.addEventListener(
            "click",
            () => {
                showView(
                    button.dataset.view
                );
            }
        );
    }
}


async function loadMatch() {
    try {
        const data =
            await fetchJSON(
                `/api/fixtures/${fixtureId}`
            );

        await loadBranding();

        const fixture =
            data.fixture;

        const [
            standingsData,
            seasonFixturesData,
            historyFixturesData
        ] = await Promise.all(
            [
                fetchJSON(
                    `/api/standings?league_id=${fixture.league_id}&season=${fixture.season}`
                ),

                fetchJSON(
                    `/api/fixtures?league_id=${fixture.league_id}&season=${fixture.season}&limit=500`
                ),

                fetchJSON(
                    `/api/fixtures?league_id=${fixture.league_id}&limit=500`
                )
            ]
        );

        renderFixture(
            data,
            standingsData.standings
            || []
        );

        renderMatchContext(
            fixture,
            seasonFixturesData.fixtures
            || [],
            historyFixturesData.fixtures
            || []
        );

    } catch (error) {
        console.error(
            error
        );

        statisticsContainer.innerHTML = `
            <div class="no-statistics">
                Could not load match data.
            </div>
        `;

        homeRecentMatches.innerHTML = `
            <div class="recent-empty">
                Could not load recent form.
            </div>
        `;

        awayRecentMatches.innerHTML = `
            <div class="recent-empty">
                Could not load recent form.
            </div>
        `;

        h2hContainer.innerHTML = `
            <div class="recent-empty">
                Could not load head-to-head data.
            </div>
        `;
    }
}


setupNavigation();

loadMatch();
