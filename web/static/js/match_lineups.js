const lineupsContainer =
    document.getElementById(
        "lineups-container"
    );

const lineupMatchPage =
    document.getElementById(
        "match-page"
    );

const lineupFixtureId = Number(
    lineupMatchPage.dataset.fixtureId
);


async function fetchLineupJSON(url) {
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


function createLineupPlayerRow(
    player,
    season
) {
    const row =
        document.createElement(
            "div"
        );

    row.className =
        "lineup-player-row";


    const number =
        document.createElement(
            "span"
        );

    number.className =
        "lineup-player-number";

    number.textContent =
        (
            player.number !== null
            && player.number !== undefined
        )
            ? player.number
            : "-";


    const identity =
        document.createElement(
            "div"
        );

    identity.className =
        "lineup-player-identity";


    let nameElement;

    if (player.player_id) {
        nameElement =
            document.createElement(
                "a"
            );

        nameElement.href =
            `/players/${player.player_id}?season=${season}`;

    } else {
        nameElement =
            document.createElement(
                "span"
            );
    }


    nameElement.className =
        "lineup-player-name";

    nameElement.textContent =
        player.player_name
        || "Unknown player";


    identity.appendChild(
        nameElement
    );


    const meta =
        document.createElement(
            "span"
        );

    meta.className =
        "lineup-player-meta";


    const pieces = [];


    if (player.position) {
        pieces.push(
            player.position
        );
    }


    if (player.grid) {
        pieces.push(
            `grid ${player.grid}`
        );
    }


    meta.textContent =
        pieces.length
            ? pieces.join(" · ")
            : "Position unavailable";


    identity.appendChild(
        meta
    );


    row.appendChild(
        number
    );

    const portrait = document.createElement("span");
    portrait.className = "lineup-player-portrait";
    portrait.setAttribute("aria-hidden", "true");
    portrait.textContent = (player.player_name || "?")
        .split(/\s+/).map(part => part[0]).slice(0, 2).join("");

    if (player.photo_url) {
        const photo = document.createElement("img");
        photo.src = player.photo_url;
        photo.alt = "";
        photo.width = 36;
        photo.height = 36;
        photo.loading = "lazy";
        photo.addEventListener("error", () => photo.remove(), {once: true});
        portrait.appendChild(photo);
    }
    row.appendChild(portrait);

    row.appendChild(
        identity
    );


    return row;
}


function createLineupSection(
    title,
    players,
    season
) {
    const section =
        document.createElement(
            "section"
        );

    section.className =
        "lineup-player-section";


    const heading =
        document.createElement(
            "div"
        );

    heading.className =
        "lineup-player-section-heading";


    const headingTitle =
        document.createElement(
            "h4"
        );

    headingTitle.textContent =
        title;


    const count =
        document.createElement(
            "span"
        );

    count.textContent =
        players.length;


    heading.appendChild(
        headingTitle
    );

    heading.appendChild(
        count
    );


    section.appendChild(
        heading
    );


    const list =
        document.createElement(
            "div"
        );

    list.className =
        "lineup-player-list";


    if (!players.length) {
        list.innerHTML = `
            <div class="lineup-empty-list">
                No players listed.
            </div>
        `;

    } else {
        for (const player of players) {
            list.appendChild(
                createLineupPlayerRow(
                    player,
                    season
                )
            );
        }
    }


    section.appendChild(
        list
    );


    return section;
}


function createLineupPitch(lineup, season) {
    const layout = LineupPositions.formationRows(lineup.starting_xi || [], lineup.formation);
    if (!layout) return createLineupSection("Starting XI", lineup.starting_xi || [], season);
    const section = document.createElement("section");
    section.className = "lineup-pitch-section";
    const pitch = document.createElement("div");
    pitch.className = "lineup-pitch";
    pitch.setAttribute("aria-label", `${lineup.team_name} starting XI, ${lineup.formation || "formation"}`);
    const markings = document.createElement("div");
    markings.className = "pitch-markings";
    markings.setAttribute("aria-hidden", "true");
    markings.innerHTML = '<span class="pitch-halfway"></span><span class="pitch-circle"></span><span class="pitch-box top"></span><span class="pitch-box bottom"></span>';
    pitch.appendChild(markings);
    for (const players of layout.rows) {
        const line = document.createElement("div");
        line.className = "pitch-player-line";
        line.style.gridTemplateColumns = `repeat(${players.length}, minmax(0, 1fr))`;
        for (const player of players) {
            const token = document.createElement(player.player_id ? "a" : "div");
            token.className = "pitch-player";
            if (player.player_id) token.href = `/players/${player.player_id}?season=${season}`;
            token.title = `${player.number ?? "-"} ${player.player_name || "Unknown player"}`;
            token.setAttribute("aria-label", token.title);
            const row = createLineupPlayerRow(player, season);
            const photo = row.querySelector(".lineup-player-portrait");
            const number = row.querySelector(".lineup-player-number");
            const name = document.createElement("span");
            name.className = "pitch-player-name";
            name.textContent = player.player_name || "Unknown player";
            token.append(photo, number, name);
            line.appendChild(token);
        }
        pitch.appendChild(line);
    }
    section.appendChild(pitch);
    if (layout.estimated) {
        const note = document.createElement("p");
        note.className = "lineup-position-note";
        note.textContent = "Positions based on formation; exact positions unavailable.";
        section.appendChild(note);
    }
    return section;
}


function createLineupTeamCard(
    lineup,
    season
) {
    const card =
        document.createElement(
            "article"
        );

    card.className =
        "lineup-team-card";


    const header =
        document.createElement(
            "header"
        );

    header.className =
        "lineup-team-header";


    const teamMain =
        document.createElement(
            "div"
        );

    teamMain.className =
        "lineup-team-main";


    if (lineup.team_logo_url) {
        const teamLogo =
            document.createElement(
                "img"
            );

        teamLogo.src =
            lineup.team_logo_url;

        teamLogo.alt =
            lineup.team_name
            || "Team";

        teamLogo.loading =
            "lazy";

        teamLogo.className =
            "lineup-team-logo";

        teamLogo.addEventListener(
            "error",
            () => {
                teamLogo.remove();
            }
        );

        teamMain.appendChild(
            teamLogo
        );
    }


    const teamBlock =
        document.createElement(
            "div"
        );

    teamBlock.className =
        "lineup-team-identity";


    const teamName =
        document.createElement(
            "a"
        );

    teamName.href =
        `/teams/${lineup.team_id}?season=${season}`;

    teamName.className =
        "lineup-team-name";

    teamName.textContent =
        lineup.team_name
        || "Team";


    teamBlock.appendChild(
        teamName
    );


    const formation =
        document.createElement(
            "span"
        );

    formation.className =
        "lineup-formation";

    formation.textContent =
        lineup.formation
            ? `Formation ${lineup.formation}`
            : "Formation unavailable";


    teamBlock.appendChild(
        formation
    );

    teamMain.appendChild(
        teamBlock
    );


    const coach =
        document.createElement(
            "div"
        );

    coach.className =
        "lineup-coach";


    const coachLabel =
        document.createElement(
            "span"
        );

    coachLabel.textContent =
        "Coach";


    const coachName =
        document.createElement(
            "strong"
        );

    coachName.textContent =
        lineup.coach?.name
        || "-";


    coach.appendChild(
        coachLabel
    );

    coach.appendChild(
        coachName
    );


    header.appendChild(
        teamMain
    );

    header.appendChild(
        coach
    );


    card.appendChild(
        header
    );


    card.appendChild(
        createLineupPitch(lineup, season)
    );


    card.appendChild(
        createLineupSection(
            "Substitutes",
            lineup.substitutes || [],
            season
        )
    );


    return card;
}


function renderLineups(data) {
    lineupsContainer.innerHTML =
        "";


    if (
        !data.available
        || !Array.isArray(
            data.lineups
        )
        || data.lineups.length === 0
    ) {
        lineupsContainer.innerHTML = `
            <div class="lineups-message">
                Lineup data is not available for this fixture.
            </div>
        `;

        return;
    }


    const grid =
        document.createElement(
            "div"
        );

    grid.className =
        "lineups-grid";


    for (const lineup of data.lineups) {
        grid.appendChild(
            createLineupTeamCard(
                lineup,
                data.season
            )
        );
    }


    lineupsContainer.appendChild(
        grid
    );
}


async function loadLineups() {
    if (!lineupsContainer) {
        return;
    }


    try {
        const data =
            await fetchLineupJSON(
                `/api/fixtures/${lineupFixtureId}/lineups`
            );


        renderLineups(
            data
        );

    } catch (error) {
        console.error(
            error
        );


        lineupsContainer.innerHTML = `
            <div class="lineups-message error">
                Could not load lineups.
            </div>
        `;
    }
}


loadLineups();
