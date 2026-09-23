const playerPage = document.getElementById(
    "player-page"
);

const playerId = Number(
    playerPage.dataset.playerId
);

const season = Number(
    playerPage.dataset.season
);


const playerBackLink = document.getElementById(
    "player-back-link"
);

const playerPhotoContainer = document.getElementById(
    "player-photo-container"
);

const playerPhotoFallback = document.getElementById(
    "player-photo-fallback"
);

const playerCompetitionLink = document.getElementById(
    "player-competition-link"
);

const playerCompetitionLogo = document.getElementById(
    "player-competition-logo"
);

const playerCompetitionName = document.getElementById(
    "player-competition-name"
);

const playerName = document.getElementById(
    "player-name"
);

const playerNationalityFlag = document.getElementById(
    "player-nationality-flag"
);

const playerNationalityName = document.getElementById(
    "player-nationality-name"
);

const playerSeason = document.getElementById(
    "player-season"
);

const playerHeaderTeams = document.getElementById(
    "player-header-teams"
);

const playerPrimaryPosition = document.getElementById(
    "player-primary-position"
);

const playerPrimaryNumber = document.getElementById(
    "player-primary-number"
);

const playerAppearances = document.getElementById(
    "player-appearances"
);

const playerStarts = document.getElementById(
    "player-starts"
);

const playerMinutes = document.getElementById(
    "player-minutes"
);

const playerGoals = document.getElementById(
    "player-goals"
);

const playerAssists = document.getElementById(
    "player-assists"
);

const playerContributions = document.getElementById(
    "player-contributions"
);

const detailBirthDate = document.getElementById(
    "detail-birth-date"
);

const detailHeight = document.getElementById(
    "detail-height"
);

const detailWeight = document.getElementById(
    "detail-weight"
);

const detailNationality = document.getElementById(
    "detail-nationality"
);

const detailPosition = document.getElementById(
    "detail-position"
);

const detailSquadNumber = document.getElementById(
    "detail-squad-number"
);

const playerStatisticsSummary = document.getElementById(
    "player-statistics-summary"
);

const playerTeamStatistics = document.getElementById(
    "player-team-statistics"
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


function getCompetitionBranding(leagueId) {
    return (
        brandingData
        ?.sports
        ?.football
        ?.competitions
        ?.[String(leagueId)]
        || null
    );
}


function getCountryByName(name) {
    if (
        !name
        || !brandingData?.countries
    ) {
        return null;
    }

    const normalized =
        name.trim().toLowerCase();

    return (
        Object.values(
            brandingData.countries
        ).find(
            country =>
                country.name
                ?.trim()
                .toLowerCase()
                === normalized
        )
        || null
    );
}


function formatSeason(value) {
    return `${value}/${String(
        value + 1
    ).slice(-2)}`;
}


function getInitials(name) {
    if (!name) {
        return "?";
    }

    const words = name
        .trim()
        .split(/\s+/);

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


function formatBirthDate(value) {
    if (!value) {
        return "-";
    }

    const date = new Date(
        `${value}T00:00:00`
    );

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            day: "numeric",
            month: "long",
            year: "numeric"
        }
    ).format(
        date
    );
}


function formatValue(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    return value;
}


function formatDecimal(
    value,
    digits = 2
) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    return Number(
        value
    ).toFixed(
        digits
    );
}


function renderPhoto(player) {
    playerPhotoFallback.textContent =
        getInitials(
            player.player_name
        );

    const oldImage =
        playerPhotoContainer.querySelector(
            ".player-header-image"
        );

    if (oldImage) {
        oldImage.remove();
    }

    playerPhotoFallback.style.display =
        "flex";

    if (!player.photo_url) {
        return;
    }

    const image = document.createElement(
        "img"
    );

    image.className =
        "player-header-image";

    image.src =
        player.photo_url;

    image.alt =
        player.player_name;

    image.loading =
        "eager";

    image.addEventListener(
        "load",
        () => {
            playerPhotoFallback.style.display =
                "none";
        }
    );

    image.addEventListener(
        "error",
        () => {
            image.remove();
        }
    );

    playerPhotoContainer.appendChild(
        image
    );
}


function renderNationality(player) {
    const country = getCountryByName(
        player.nationality
    );

    playerNationalityName.textContent =
        player.nationality
        || "Unknown nationality";

    playerNationalityFlag.innerHTML =
        "";

    if (!country?.flag_url) {
        return;
    }

    const image = document.createElement(
        "img"
    );

    image.src =
        country.flag_url;

    image.alt =
        player.nationality;

    image.loading =
        "eager";

    playerNationalityFlag.appendChild(
        image
    );
}


function renderCompetition(
    leagueId,
    currentSeason
) {
    const competition =
        getCompetitionBranding(
            leagueId
        );

    playerCompetitionLink.href =
        `/competitions/${leagueId}?season=${currentSeason}`;

    playerCompetitionName.textContent =
        competition?.name
        || "Premier League";

    playerCompetitionLogo.innerHTML =
        "";

    if (competition?.logo_url) {
        const image = document.createElement(
            "img"
        );

        image.src =
            competition.logo_url;

        image.alt =
            competition.name;

        image.loading =
            "eager";

        playerCompetitionLogo.appendChild(
            image
        );
    }
}


function createTeamChip(statistics) {
    const link = document.createElement(
        "a"
    );

    link.href =
        `/teams/${statistics.team_id}?season=${season}`;

    link.className =
        "player-header-team entity-trigger";

    link.dataset.entityType =
        "team";

    link.dataset.entityId =
        statistics.team_id;

    link.dataset.season =
        season;

    const branding =
        getTeamBranding(
            statistics.team_id
        );

    if (branding?.logo_url) {
        const logo = document.createElement(
            "img"
        );

        logo.src =
            branding.logo_url;

        logo.alt =
            statistics.team_name;

        logo.className =
            "entity-team-logo-inline";

        logo.loading =
            "lazy";

        link.appendChild(
            logo
        );
    }

    const name = document.createElement(
        "span"
    );

    name.textContent =
        statistics.team_name;

    link.appendChild(
        name
    );

    return link;
}


function renderHeaderTeams(statistics) {
    playerHeaderTeams.innerHTML =
        "";

    if (
        !statistics
        || statistics.length === 0
    ) {
        playerHeaderTeams.innerHTML = `
            <span class="player-no-team">
                No team data for this season
            </span>
        `;

        return;
    }

    for (
        const teamStatistics
        of statistics
    ) {
        playerHeaderTeams.appendChild(
            createTeamChip(
                teamStatistics
            )
        );
    }
}


function getPrimaryStatistics(statistics) {
    if (
        !statistics
        || statistics.length === 0
    ) {
        return null;
    }

    return [...statistics].sort(
        (a, b) =>
            (b.minutes || 0)
            - (a.minutes || 0)
    )[0];
}


function renderProfileDetails(
    player,
    primaryStatistics
) {
    detailBirthDate.textContent =
        formatBirthDate(
            player.birth_date
        );

    detailHeight.textContent =
        player.height_cm
            ? `${player.height_cm} cm`
            : "-";

    detailWeight.textContent =
        player.weight_kg
            ? `${player.weight_kg} kg`
            : "-";

    detailNationality.textContent =
        player.nationality
        || "-";

    detailPosition.textContent =
        primaryStatistics?.position
        || "-";

    detailSquadNumber.textContent =
        primaryStatistics?.squad_number
        !== null
        && primaryStatistics?.squad_number
        !== undefined
            ? `#${primaryStatistics.squad_number}`
            : "-";
}


function createDetailStat(
    name,
    value
) {
    const item = document.createElement(
        "div"
    );

    item.className =
        "player-detail-stat";

    const label = document.createElement(
        "span"
    );

    label.textContent =
        name;

    const number = document.createElement(
        "strong"
    );

    number.textContent =
        formatValue(
            value
        );

    item.appendChild(
        label
    );

    item.appendChild(
        number
    );

    return item;
}


function createStatisticsGroup(
    title,
    items
) {
    const availableItems =
        items.filter(
            item =>
                item[1] !== null
                && item[1] !== undefined
        );

    if (
        availableItems.length === 0
    ) {
        return null;
    }

    const group = document.createElement(
        "section"
    );

    group.className =
        "player-stat-group";

    const heading = document.createElement(
        "h4"
    );

    heading.textContent =
        title;

    const grid = document.createElement(
        "div"
    );

    grid.className =
        "player-detail-grid";

    for (
        const [
            name,
            value
        ]
        of availableItems
    ) {
        grid.appendChild(
            createDetailStat(
                name,
                value
            )
        );
    }

    group.appendChild(
        heading
    );

    group.appendChild(
        grid
    );

    return group;
}


function createTeamStatistics(statistics) {
    const section = document.createElement(
        "section"
    );

    section.className =
        "player-team-section";

    const header = document.createElement(
        "div"
    );

    header.className =
        "player-team-header";

    const teamIdentity = document.createElement(
        "div"
    );

    teamIdentity.className =
        "player-team-identity";

    const teamLink = document.createElement(
        "a"
    );

    teamLink.className =
        "player-team-link entity-trigger";

    teamLink.href =
        `/teams/${statistics.team_id}?season=${season}`;

    teamLink.dataset.entityType =
        "team";

    teamLink.dataset.entityId =
        statistics.team_id;

    teamLink.dataset.season =
        season;

    const branding =
        getTeamBranding(
            statistics.team_id
        );

    if (branding?.logo_url) {
        const logo = document.createElement(
            "img"
        );

        logo.src =
            branding.logo_url;

        logo.alt =
            statistics.team_name;

        logo.className =
            "entity-team-logo-inline player-team-logo";

        logo.loading =
            "lazy";

        teamLink.appendChild(
            logo
        );
    }

    const teamName = document.createElement(
        "span"
    );

    teamName.textContent =
        statistics.team_name;

    teamLink.appendChild(
        teamName
    );

    const subline = document.createElement(
        "div"
    );

    subline.className =
        "player-team-subline";

    subline.textContent = [
        statistics.position,
        statistics.squad_number !== null
            && statistics.squad_number !== undefined
            ? `#${statistics.squad_number}`
            : null,
        statistics.statistics_available === false ? "Season statistics unavailable" : `${statistics.appearances ?? 0} appearances`
    ]
        .filter(Boolean)
        .join(" · ");

    teamIdentity.appendChild(
        teamLink
    );

    teamIdentity.appendChild(
        subline
    );

    const rating = document.createElement(
        "div"
    );

    rating.className =
        "player-rating";

    rating.innerHTML = `
        <span>
            Rating
        </span>

        <strong>
            ${formatDecimal(
                statistics.rating
            )}
        </strong>
    `;

    header.appendChild(
        teamIdentity
    );

    header.appendChild(
        rating
    );

    const content = document.createElement(
        "div"
    );

    content.className =
        "player-team-content";

    if (statistics.statistics_available === false) {
        content.textContent = "Squad member. No season statistics supplied by the provider.";
        section.append(header, content);
        return section;
    }

    const overviewGroup = createStatisticsGroup(
        "Overview",
        [
            [
                "Appearances",
                statistics.appearances
            ],
            [
                "Starts",
                statistics.lineups
            ],
            [
                "Minutes",
                statistics.minutes
            ],
            [
                "Subbed in",
                statistics.substitutes_in
            ],
            [
                "Subbed out",
                statistics.substitutes_out
            ]
        ]
    );

    const attackingGroup = createStatisticsGroup(
        "Attacking",
        [
            [
                "Goals",
                statistics.goals_total
            ],
            [
                "Assists",
                statistics.assists
            ],
            [
                "Shots",
                statistics.shots_total
            ],
            [
                "Shots on target",
                statistics.shots_on_goal
            ],
            [
                "Dribble attempts",
                statistics.dribbles_attempts
            ],
            [
                "Successful dribbles",
                statistics.dribbles_success
            ]
        ]
    );

    const passingGroup = createStatisticsGroup(
        "Passing",
        [
            [
                "Passes",
                statistics.passes_total
            ],
            [
                "Key passes",
                statistics.key_passes
            ],
            [
                "Pass accuracy",
                statistics.pass_accuracy !== null
                    && statistics.pass_accuracy !== undefined
                    ? `${formatDecimal(
                        statistics.pass_accuracy,
                        1
                    )}%`
                    : null
            ]
        ]
    );

    const defendingGroup = createStatisticsGroup(
        "Defending & duels",
        [
            [
                "Tackles",
                statistics.tackles_total
            ],
            [
                "Blocks",
                statistics.blocks
            ],
            [
                "Interceptions",
                statistics.interceptions
            ],
            [
                "Duels",
                statistics.duels_total
            ],
            [
                "Duels won",
                statistics.duels_won
            ],
            [
                "Dribbled past",
                statistics.dribbled_past
            ]
        ]
    );

    const disciplineGroup = createStatisticsGroup(
        "Discipline",
        [
            [
                "Fouls drawn",
                statistics.fouls_drawn
            ],
            [
                "Fouls committed",
                statistics.fouls_committed
            ],
            [
                "Yellow cards",
                statistics.yellow_cards
            ],
            [
                "Second yellow",
                statistics.yellow_red_cards
            ],
            [
                "Red cards",
                statistics.red_cards
            ]
        ]
    );

    const penaltyGroup = createStatisticsGroup(
        "Penalties",
        [
            [
                "Won",
                statistics.penalties_won
            ],
            [
                "Committed",
                statistics.penalties_committed
            ],
            [
                "Scored",
                statistics.penalties_scored
            ],
            [
                "Missed",
                statistics.penalties_missed
            ],
            [
                "Saved",
                statistics.penalties_saved
            ]
        ]
    );

    const isGoalkeeper =
        statistics.position
        && statistics.position
            .toLowerCase()
            .includes(
                "goal"
            );

    let goalkeeperGroup = null;

    if (isGoalkeeper) {
        goalkeeperGroup = createStatisticsGroup(
            "Goalkeeping",
            [
                [
                    "Saves",
                    statistics.saves
                ],
                [
                    "Goals conceded",
                    statistics.goals_conceded
                ]
            ]
        );
    }

    const groups = [
        overviewGroup,
        attackingGroup,
        passingGroup,
        defendingGroup,
        disciplineGroup,
        penaltyGroup,
        goalkeeperGroup
    ];

    for (
        const group
        of groups
    ) {
        if (group) {
            content.appendChild(
                group
            );
        }
    }

    section.appendChild(
        header
    );

    section.appendChild(
        content
    );

    return section;
}


function renderPlayer(data) {
    const player =
        data.player;

    const summary =
        data.summary || {};

    const statistics =
        data.statistics || [];
    const hasSeasonStatistics = statistics.some(row => row.statistics_available !== false);

    const primaryStatistics =
        getPrimaryStatistics(
            statistics
        );

    const competition =
        getCompetitionBranding(
            data.league_id
        );

    const competitionName =
        competition?.name
        || "Premier League";

    document.title =
        `${player.player_name} | PL Analytics`;

    playerName.textContent =
        player.player_name;

    playerSeason.textContent =
        `${formatSeason(
            data.season
        )} season`;

    renderPhoto(
        player
    );

    renderNationality(
        player
    );

    renderCompetition(
        data.league_id,
        data.season
    );

    renderHeaderTeams(
        statistics
    );

    playerPrimaryPosition.textContent =
        primaryStatistics?.position
        || "-";

    playerPrimaryNumber.textContent =
        primaryStatistics?.squad_number
        !== null
        && primaryStatistics?.squad_number
        !== undefined
            ? `#${primaryStatistics.squad_number}`
            : "-";

    playerAppearances.textContent =
        summary.appearances
        ?? 0;

    playerStarts.textContent =
        summary.lineups
        ?? 0;

    playerMinutes.textContent =
        summary.minutes
        ?? 0;

    playerGoals.textContent =
        summary.goals
        ?? 0;

    playerAssists.textContent =
        summary.assists
        ?? 0;

    playerContributions.textContent =
        Number(
            summary.goals
            || 0
        )
        + Number(
            summary.assists
            || 0
        );

    if (!hasSeasonStatistics) {
        for (const field of [playerAppearances, playerStarts, playerMinutes, playerGoals, playerAssists, playerContributions]) field.textContent = "-";
    }

    renderProfileDetails(
        player,
        primaryStatistics
    );

    playerTeamStatistics.innerHTML =
        "";

    if (
        statistics.length === 0
    ) {
        playerStatisticsSummary.textContent =
            `No ${competitionName} appearances in this season`;

        playerTeamStatistics.innerHTML = `
            <div class="empty-message">
                No player statistics available for this season.
            </div>
        `;

        playerBackLink.href =
            `/competitions/${data.league_id}?season=${data.season}`;

        playerBackLink.textContent =
            `← Back to ${competitionName}`;

        return;
    }

    if (
        statistics.length === 1
    ) {
        playerStatisticsSummary.textContent =
            `${competitionName} statistics for ${statistics[0].team_name}`;

        playerBackLink.href =
            `/teams/${statistics[0].team_id}?season=${data.season}`;

        playerBackLink.textContent =
            `← Back to ${statistics[0].team_name}`;

    } else {
        playerStatisticsSummary.textContent =
            `${competitionName} statistics across ${statistics.length} teams`;

        playerBackLink.href =
            `/competitions/${data.league_id}?season=${data.season}`;

        playerBackLink.textContent =
            `← Back to ${competitionName}`;
    }

    for (
        const teamStatistics
        of statistics
    ) {
        playerTeamStatistics.appendChild(
            createTeamStatistics(
                teamStatistics
            )
        );
    }
}


async function loadPlayer() {
    try {
        const [
            data
        ] = await Promise.all(
            [
                fetchJSON(
                    `/api/players/${playerId}?season=${season}`
                ),
                loadBranding()
            ]
        );

        renderPlayer(
            data
        );

    } catch (error) {
        console.error(
            error
        );

        playerName.textContent =
            "Could not load player";

        playerStatisticsSummary.textContent =
            "Player data could not be loaded";

        playerTeamStatistics.innerHTML = `
            <div class="error-message">
                Could not load player statistics.
            </div>
        `;
    }
}


loadPlayer();
