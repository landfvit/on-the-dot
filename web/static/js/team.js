const teamPage = document.getElementById(
    "team-page"
);

const teamId = Number(
    teamPage.dataset.teamId
);

const season = Number(
    teamPage.dataset.season
);


const teamBackLink = document.getElementById(
    "team-back-link"
);

const teamBadge = document.getElementById(
    "team-badge"
);

const teamCompetitionLink = document.getElementById(
    "team-competition-link"
);

const teamCompetitionLogo = document.getElementById(
    "team-competition-logo"
);

const teamCompetitionName = document.getElementById(
    "team-competition-name"
);

const teamName = document.getElementById(
    "team-name"
);

const teamCountryFlag = document.getElementById(
    "team-country-flag"
);

const teamCountryName = document.getElementById(
    "team-country-name"
);

const teamSeason = document.getElementById(
    "team-season"
);

const teamForm = document.getElementById(
    "team-form"
);

const leaguePosition = document.getElementById(
    "league-position"
);

const leaguePositionContext = document.getElementById(
    "league-position-context"
);

const teamPoints = document.getElementById(
    "team-points"
);

const matchesPlayed = document.getElementById(
    "matches-played"
);

const teamRecord = document.getElementById(
    "team-record"
);

const goalDifference = document.getElementById(
    "goal-difference"
);

const goalsFor = document.getElementById(
    "goals-for"
);

const goalsAgainst = document.getElementById(
    "goals-against"
);

const statisticsCoverage = document.getElementById(
    "statistics-coverage"
);

const shootingStatistics = document.getElementById(
    "shooting-statistics"
);

const passingStatistics = document.getElementById(
    "passing-statistics"
);

const activityStatistics = document.getElementById(
    "activity-statistics"
);

const disciplineStatistics = document.getElementById(
    "discipline-statistics"
);

const squadSummary = document.getElementById(
    "squad-summary"
);

const squadContainer = document.getElementById(
    "squad-container"
);

const recentMatches = document.getElementById(
    "recent-matches"
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


function getTeamBranding(value) {
    return (
        brandingData
        ?.sports
        ?.football
        ?.teams
        ?.[String(value)]
        || null
    );
}


function getCompetitionBranding(value) {
    return (
        brandingData
        ?.sports
        ?.football
        ?.competitions
        ?.[String(value)]
        || null
    );
}


function getCountryByCode(code) {
    if (!code) {
        return null;
    }

    return (
        brandingData
        ?.countries
        ?.[code]
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


function formatGoalDifference(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    if (value > 0) {
        return `+${value}`;
    }

    return String(
        value
    );
}


function formatStatValue(
    value,
    suffix = ""
) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    const number = Number(
        value
    );

    if (suffix === "%") {
        return `${number.toFixed(1)}%`;
    }

    if (number >= 100) {
        return number.toFixed(
            0
        );
    }

    return number.toFixed(
        2
    );
}


function formatTotal(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "-";
    }

    return Number(
        value
    ).toFixed(
        0
    );
}


function formatMatchDate(value) {
    const date = new Date(
        value
    );

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            day: "numeric",
            month: "short"
        }
    ).format(
        date
    );
}


function renderTeamLogo(
    container,
    branding,
    fallback,
    fallbackLogoUrl = null
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
            branding?.name
            || fallback;

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


function renderCompetitionBranding(
    leagueId,
    currentSeason
) {
    const competition =
        getCompetitionBranding(
            leagueId
        );

    teamCompetitionLink.href =
        `/competitions/${leagueId}?season=${currentSeason}`;

    teamBackLink.href =
        `/competitions/${leagueId}?season=${currentSeason}`;

    teamCompetitionName.textContent =
        competition?.name
        || "Premier League";

    teamBackLink.textContent =
        `← Back to ${competition?.name || "competition"}`;

    teamCompetitionLogo.innerHTML =
        "";

    if (
        competition
        && competition.logo_url
    ) {
        const image =
            document.createElement(
                "img"
            );

        image.src =
            competition.logo_url;

        image.alt =
            competition.name;

        image.loading =
            "eager";

        teamCompetitionLogo.appendChild(
            image
        );
    }
}


function renderCountry(
    branding,
    team = null
) {
    const country =
        getCountryByCode(
            branding?.country_code
            || team?.country_code
        )
        || getCountryByName(
            branding?.country_name
            || team?.country_name
        );

    const countryName =
        branding?.country_name
        || team?.country_name
        || country?.name
        || "Unknown country";

    const flagUrl =
        country?.flag_url
        || null;

    teamCountryName.textContent =
        countryName;

    teamCountryFlag.innerHTML =
        "";

    if (!flagUrl) {
        return;
    }

    const flag =
        document.createElement(
            "img"
        );

    flag.src =
        flagUrl;

    flag.alt =
        countryName;

    flag.loading =
        "eager";

    teamCountryFlag.appendChild(
        flag
    );
}


function getMatchResult(
    match,
    currentTeamId
) {
    const isHome =
        Number(
            match.home_team_id
        ) === Number(
            currentTeamId
        );

    const teamGoals =
        isHome
            ? match.home_goals
            : match.away_goals;

    const opponentGoals =
        isHome
            ? match.away_goals
            : match.home_goals;

    if (
        teamGoals === null
        || teamGoals === undefined
        || opponentGoals === null
        || opponentGoals === undefined
    ) {
        return {
            label: "-",
            className: "unknown"
        };
    }

    if (
        teamGoals > opponentGoals
    ) {
        return {
            label: "W",
            className: "win"
        };
    }

    if (
        teamGoals < opponentGoals
    ) {
        return {
            label: "L",
            className: "loss"
        };
    }

    return {
        label: "D",
        className: "draw"
    };
}


function renderForm(
    matches
) {
    teamForm.innerHTML =
        "";

    const finished =
        matches
        .filter(
            match =>
                match.status === "FT"
        )
        .slice(
            0,
            5
        )
        .reverse();

    if (
        finished.length === 0
    ) {
        teamForm.innerHTML = `
            <span class="team-form-empty">
                No recent matches
            </span>
        `;

        return;
    }

    for (
        const match
        of finished
    ) {
        const result =
            getMatchResult(
                match,
                teamId
            );

        const badge =
            document.createElement(
                "span"
            );

        badge.className =
            `team-form-result ${result.className}`;

        badge.textContent =
            result.label;

        badge.title =
            `${match.home_team} ${match.home_goals}:${match.away_goals} ${match.away_team}`;

        teamForm.appendChild(
            badge
        );
    }
}


function createStatCard(
    statistic,
    team
) {
    const card =
        document.createElement(
            "article"
        );

    card.className =
        "stat-card";

    let rankText =
        "No rank";

    if (
        statistic.rank !== null
        && statistic.rank !== undefined
    ) {
        rankText =
            `#${statistic.rank} / ${team.league_team_count}`;
    }

    const completeCoverage =
        team.matches_with_stats
        === team.matches_played;

    let details = `
        <div class="stat-detail">

            <span>
                Average
            </span>

            <strong>
                ${formatStatValue(
                    statistic.value,
                    statistic.suffix || ""
                )}
            </strong>

        </div>
    `;

    if (
        statistic.total !== undefined
    ) {
        const totalLabel =
            completeCoverage
                ? "Season total"
                : "Recorded total";

        details = `
            <div class="stat-detail">

                <span>
                    ${totalLabel}
                </span>

                <strong>
                    ${formatTotal(
                        statistic.total
                    )}
                </strong>

            </div>

            <div class="stat-detail">

                <span>
                    Per match
                </span>

                <strong>
                    ${formatStatValue(
                        statistic.value
                    )}
                </strong>

            </div>
        `;
    }

    card.innerHTML = `
        <div class="stat-card-header">

            <span class="stat-name">
                ${statistic.name}
            </span>

            <span class="stat-rank">
                ${rankText}
            </span>

        </div>

        <div class="stat-primary-value">
            ${formatStatValue(
                statistic.value,
                statistic.suffix || ""
            )}
        </div>

        <div class="stat-details">
            ${details}
        </div>
    `;

    return card;
}


function renderStatGroup(
    container,
    statistics,
    team
) {
    container.innerHTML =
        "";

    const availableStatistics =
        statistics.filter(
            statistic =>
                statistic.value !== null
                && statistic.value !== undefined
        );

    if (
        availableStatistics.length === 0
    ) {
        container.innerHTML = `
            <div class="no-statistics">
                No detailed statistics available.
            </div>
        `;

        return;
    }

    for (
        const statistic
        of availableStatistics
    ) {
        container.appendChild(
            createStatCard(
                statistic,
                team
            )
        );
    }
}


function renderStatistics(team) {
    const shooting = [
        {
            name: "Total shots",
            total: team.season_total_shots,
            value: team.avg_total_shots,
            rank: team.total_shots_rank
        },
        {
            name: "Shots on goal",
            total: team.season_total_shots_on_goal,
            value: team.avg_shots_on_goal,
            rank: team.shots_on_goal_rank
        },
        {
            name: "Shots off goal",
            total: team.season_total_shots_off_goal,
            value: team.avg_shots_off_goal,
            rank: team.shots_off_goal_rank
        },
        {
            name: "Blocked shots",
            total: team.season_total_blocked_shots,
            value: team.avg_blocked_shots,
            rank: team.blocked_shots_rank
        },
        {
            name: "Shots inside box",
            total: team.season_total_shots_inside_box,
            value: team.avg_shots_inside_box,
            rank: team.shots_inside_box_rank
        },
        {
            name: "Shots outside box",
            total: team.season_total_shots_outside_box,
            value: team.avg_shots_outside_box,
            rank: team.shots_outside_box_rank
        }
    ];

    const passing = [
        {
            name: "Ball possession",
            value: team.avg_ball_possession,
            rank: team.ball_possession_rank,
            suffix: "%"
        },
        {
            name: "Total passes",
            total: team.season_total_passes,
            value: team.avg_total_passes,
            rank: team.total_passes_rank
        },
        {
            name: "Accurate passes",
            total: team.season_total_passes_accurate,
            value: team.avg_passes_accurate,
            rank: team.passes_accurate_rank
        },
        {
            name: "Pass accuracy",
            value: team.avg_passes_percentage,
            rank: team.passes_percentage_rank,
            suffix: "%"
        }
    ];

    const activity = [
        {
            name: "Corner kicks",
            total: team.season_total_corner_kicks,
            value: team.avg_corner_kicks,
            rank: team.corner_kicks_rank
        },
        {
            name: "Offsides",
            total: team.season_total_offsides,
            value: team.avg_offsides,
            rank: team.offsides_rank
        },
        {
            name: "Fouls",
            total: team.season_total_fouls,
            value: team.avg_fouls,
            rank: team.fouls_rank
        }
    ];

    const discipline = [
        {
            name: "Yellow cards",
            total: team.total_yellow_cards,
            value: team.avg_yellow_cards,
            rank: team.yellow_cards_rank
        },
        {
            name: "Red cards",
            total: team.total_red_cards,
            value: team.avg_red_cards,
            rank: team.red_cards_rank
        },
        {
            name: "Goalkeeper saves",
            total: team.season_total_goalkeeper_saves,
            value: team.avg_goalkeeper_saves,
            rank: team.goalkeeper_saves_rank
        }
    ];

    renderStatGroup(
        shootingStatistics,
        shooting,
        team
    );

    renderStatGroup(
        passingStatistics,
        passing,
        team
    );

    renderStatGroup(
        activityStatistics,
        activity,
        team
    );

    renderStatGroup(
        disciplineStatistics,
        discipline,
        team
    );
}


function normalizePosition(position) {
    if (!position) {
        return "Other";
    }

    const value =
        position.toLowerCase();

    if (
        value.includes(
            "goal"
        )
    ) {
        return "Goalkeepers";
    }

    if (
        value.includes(
            "def"
        )
    ) {
        return "Defenders";
    }

    if (
        value.includes(
            "mid"
        )
    ) {
        return "Midfielders";
    }

    if (
        value.includes(
            "attack"
        )
        || value.includes(
            "forward"
        )
    ) {
        return "Attackers";
    }

    return "Other";
}


function formatPlayerNumber(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "—";
    }

    return value;
}


function createPlayerPhoto(player) {
    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        "player-photo-wrapper";

    const fallback =
        document.createElement(
            "div"
        );

    fallback.className =
        "player-photo-fallback";

    fallback.textContent =
        getInitials(
            player.player_name
        );

    wrapper.appendChild(
        fallback
    );

    if (!player.photo_url) {
        return wrapper;
    }

    const image =
        document.createElement(
            "img"
        );

    image.className =
        "player-photo";

    image.src =
        player.photo_url;

    image.alt =
        player.player_name;

    image.loading =
        "lazy";

    image.addEventListener(
        "load",
        () => {
            fallback.classList.add(
                "hidden"
            );
        }
    );

    image.addEventListener(
        "error",
        () => {
            image.remove();
        }
    );

    wrapper.appendChild(
        image
    );

    return wrapper;
}


function createPlayerNationality(player) {
    const wrapper =
        document.createElement(
            "span"
        );

    wrapper.className =
        "player-nationality";

    const country =
        getCountryByName(
            player.nationality
        );

    if (
        country
        && country.flag_url
    ) {
        const flag =
            document.createElement(
                "img"
            );

        flag.src =
            country.flag_url;

        flag.alt =
            player.nationality;

        flag.loading =
            "lazy";

        wrapper.appendChild(
            flag
        );
    }

    const text =
        document.createElement(
            "span"
        );

    text.textContent =
        player.nationality
        || "Unknown nationality";

    wrapper.appendChild(
        text
    );

    return wrapper;
}


function createPlayerCard(player) {
    const card =
        document.createElement(
            "a"
        );

    card.className =
        "player-card";

    card.href =
        `/players/${player.player_id}?season=${season}`;

    card.dataset.entityType =
        "player";

    card.dataset.entityId =
        player.player_id;

    card.dataset.season =
        season;

    const top =
        document.createElement(
            "div"
        );

    top.className =
        "player-card-top";

    const photo =
        createPlayerPhoto(
            player
        );

    const identity =
        document.createElement(
            "div"
        );

    identity.className =
        "player-identity";

    const number =
        document.createElement(
            "div"
        );

    number.className =
        "player-number";

    number.textContent =
        `#${formatPlayerNumber(
            player.squad_number
        )}`;

    const name =
        document.createElement(
            "h4"
        );

    name.className =
        "player-name";

    name.textContent =
        player.player_name;

    const meta =
        document.createElement(
            "div"
        );

    meta.className =
        "player-meta";

    const position =
        document.createElement(
            "span"
        );

    position.className =
        "player-position";

    position.textContent =
        player.position
        || "Unknown position";

    meta.appendChild(
        position
    );

    meta.appendChild(
        createPlayerNationality(
            player
        )
    );

    identity.appendChild(
        number
    );

    identity.appendChild(
        name
    );

    identity.appendChild(
        meta
    );

    top.appendChild(
        photo
    );

    top.appendChild(
        identity
    );

    const stats =
        document.createElement(
            "div"
        );

    stats.className =
        "player-card-stats";

    stats.innerHTML = `
        <div class="player-stat">
            <span>Apps</span>
            <strong>${player.appearances ?? "-"}</strong>
        </div>

        <div class="player-stat">
            <span>Minutes</span>
            <strong>${player.minutes ?? "-"}</strong>
        </div>

        <div class="player-stat">
            <span>Goals</span>
            <strong>${player.goals_total ?? "-"}</strong>
        </div>

        <div class="player-stat">
            <span>Assists</span>
            <strong>${player.assists ?? "-"}</strong>
        </div>
    `;

    card.appendChild(
        top
    );

    card.appendChild(
        stats
    );

    return card;
}


function renderSquad(
    players,
    competitionName
) {
    squadContainer.innerHTML =
        "";

    if (
        !players
        || players.length === 0
    ) {
        squadContainer.innerHTML = `
            <div class="empty-message">
                No squad records available for this season.
            </div>
        `;

        squadSummary.textContent =
            "No player data available";

        return;
    }

    squadSummary.textContent =
        `${players.length} players in the ${competitionName} season squad`;

    const groups = {
        Goalkeepers: [],
        Defenders: [],
        Midfielders: [],
        Attackers: [],
        Other: []
    };

    for (
        const player
        of players
    ) {
        const group =
            normalizePosition(
                player.position
            );

        groups[
            group
        ].push(
            player
        );
    }

    const groupOrder = [
        "Goalkeepers",
        "Defenders",
        "Midfielders",
        "Attackers",
        "Other"
    ];

    for (
        const groupName
        of groupOrder
    ) {
        const groupPlayers =
            groups[
                groupName
            ];

        if (
            groupPlayers.length === 0
        ) {
            continue;
        }

        const section =
            document.createElement(
                "section"
            );

        section.className =
            "squad-group";

        const heading =
            document.createElement(
                "div"
            );

        heading.className =
            "squad-group-heading";

        heading.innerHTML = `
            <h3>
                ${groupName}
            </h3>

            <span>
                ${groupPlayers.length}
            </span>
        `;

        const grid =
            document.createElement(
                "div"
            );

        grid.className =
            "squad-grid";

        for (
            const player
            of groupPlayers
        ) {
            grid.appendChild(
                createPlayerCard(
                    player
                )
            );
        }

        section.appendChild(
            heading
        );

        section.appendChild(
            grid
        );

        squadContainer.appendChild(
            section
        );
    }
}


function createRecentTeam(
    value,
    name,
    isHome,
    logoUrl = null
) {
    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        `recent-match-team ${isHome ? "home" : "away"}`;

    const branding =
        getTeamBranding(
            value
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
            name;

        logo.className =
            "recent-match-team-logo";

        logo.loading =
            "lazy";

        wrapper.appendChild(
            logo
        );
    }

    const text =
        document.createElement(
            "span"
        );

    text.textContent =
        name;

    wrapper.appendChild(
        text
    );

    return wrapper;
}


function renderRecentMatches(
    matches
) {
    recentMatches.innerHTML =
        "";

    if (
        !matches
        || matches.length === 0
    ) {
        recentMatches.innerHTML = `
            <div class="empty-message">
                No completed matches found.
            </div>
        `;

        return;
    }

    for (
        const match
        of matches
    ) {
        const row =
            document.createElement(
                "div"
            );

        row.className =
            "recent-match";

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
            `Open match ${match.home_team} vs ${match.away_team}`
        );

        const result =
            getMatchResult(
                match,
                teamId
            );

        const date =
            document.createElement(
                "div"
            );

        date.className =
            "recent-match-date";

        date.textContent =
            formatMatchDate(
                match.match_date
            );

        const home =
            createRecentTeam(
                match.home_team_id,
                match.home_team,
                true,
                match.home_team_logo_url
            );

        const score =
            document.createElement(
                "div"
            );

        score.className =
            "recent-match-score";

        score.innerHTML = `
            <span>
                ${match.home_goals}
            </span>

            <span class="recent-score-separator">
                :
            </span>

            <span>
                ${match.away_goals}
            </span>
        `;

        const away =
            createRecentTeam(
                match.away_team_id,
                match.away_team,
                false,
                match.away_team_logo_url
            );

        const resultElement =
            document.createElement(
                "div"
            );

        resultElement.className =
            `recent-match-result ${result.className}`;

        resultElement.textContent =
            result.label;

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

        row.appendChild(
            resultElement
        );

        const openMatch = () => {
            window.location.href =
                `/matches/${match.fixture_id}`;
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

        recentMatches.appendChild(
            row
        );
    }
}


function renderUpcomingMatches(matches) {
    const container = document.getElementById("upcoming-matches");
    container.replaceChildren();
    document.getElementById("upcoming-count").textContent = `${matches.length} scheduled`;
    if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "empty-message";
        empty.textContent = "No upcoming matches scheduled for this season.";
        container.appendChild(empty);
    }
    for (const match of matches) {
        const row = document.createElement("a");
        row.className = "recent-match upcoming-match";
        row.href = `/matches/${match.fixture_id}`;
        row.setAttribute("aria-label", `${match.home_team} vs ${match.away_team}, ${formatMatchDate(match.match_date)}`);
        const date = document.createElement("time");
        date.className = "recent-match-date";
        date.dateTime = match.match_date;
        date.textContent = formatMatchDate(match.match_date);
        const kickoff = document.createElement("span");
        kickoff.className = "recent-match-score";
        kickoff.textContent = match.status === "TBD" ? "TBD" : new Date(match.match_date).toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit"});
        const arrow = document.createElement("span");
        arrow.className = "recent-match-result";
        arrow.textContent = "\u2192";
        arrow.setAttribute("aria-hidden", "true");
        row.append(date, createRecentTeam(match.home_team_id, match.home_team, true, match.home_team_logo_url), kickoff,
            createRecentTeam(match.away_team_id, match.away_team, false, match.away_team_logo_url), arrow);
        container.appendChild(row);
    }
}

function renderTeam(
    data
) {
    const team =
        data.team;

    const teamBranding =
        getTeamBranding(
            team.team_id
        );

    const competition =
        getCompetitionBranding(
            team.league_id
        );

    const competitionName =
        competition?.name
        || "Premier League";

    document.title =
        `${team.team_name} | PL Analytics`;

    teamName.textContent =
        team.team_name;

    renderTeamLogo(
        teamBadge,
        teamBranding,
        getInitials(
            team.team_name
        ),
        team.team_logo_url
    );

    renderCompetitionBranding(
        team.league_id,
        team.season
    );

    renderCountry(
        teamBranding,
        team
    );

    teamSeason.textContent =
        `${formatSeason(
            team.season
        )} season`;

    leaguePosition.textContent =
        team.league_position
            ? `#${team.league_position}`
            : "-";

    leaguePositionContext.textContent =
        team.league_team_count
            ? `of ${team.league_team_count} teams`
            : competitionName;

    teamPoints.textContent =
        team.points
        ?? "-";

    matchesPlayed.textContent =
        team.matches_played
        ?? "-";

    teamRecord.textContent =
        `${team.wins ?? 0} W · ${team.draws ?? 0} D · ${team.losses ?? 0} L`;

    goalDifference.textContent =
        formatGoalDifference(
            team.goal_difference
        );

    goalsFor.textContent =
        team.goals_for
        ?? "-";

    goalsAgainst.textContent =
        team.goals_against
        ?? "-";

    statisticsCoverage.textContent =
        `Statistics based on ${team.matches_with_stats ?? 0} of ${team.matches_played ?? 0} completed matches`;

    renderForm(
        data.recent_matches
        || []
    );

    renderStatistics(
        team
    );

    renderRecentMatches(
        data.recent_matches
        || []
    );
    renderUpcomingMatches(data.upcoming_matches || []);

    return competitionName;
}


async function loadPage() {
    try {
        const [
            teamData,
            squadData
        ] = await Promise.all(
            [
                fetchJSON(
                    `/api/teams/${teamId}?season=${season}`
                ),

                fetchJSON(
                    `/api/teams/${teamId}/players?season=${season}`
                ),

                loadBranding()
            ]
        );

        const competitionName =
            renderTeam(
                teamData
            );

        renderSquad(
            squadData.players
            || [],
            competitionName
        );

    } catch (error) {
        document.getElementById("upcoming-matches").textContent = "Could not load upcoming matches.";
        console.error(
            error
        );

        teamName.textContent =
            "Could not load team";

        statisticsCoverage.textContent =
            "Team data could not be loaded";

        squadSummary.textContent =
            "Squad data could not be loaded";

        teamForm.innerHTML = `
            <span class="team-form-empty">
                Form unavailable
            </span>
        `;

        squadContainer.innerHTML = `
            <div class="error-message">
                Could not load squad data.
            </div>
        `;

        recentMatches.innerHTML = `
            <div class="error-message">
                Could not load team data.
            </div>
        `;
    }
}


loadPage();
