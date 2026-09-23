const playersPage =
    document.getElementById(
        "players-page"
    );


const season =
    Number(
        playersPage.dataset.season
    );


const searchInput =
    document.getElementById(
        "player-search"
    );


const playersGrid =
    document.getElementById(
        "players-grid"
    );


const resultCount =
    document.getElementById(
        "players-result-count"
    );


const seasonLabel =
    document.getElementById(
        "players-season-label"
    );


let searchTimeout = null;


async function fetchJSON(url) {
    const response =
        await fetch(
            url
        );


    if (!response.ok) {
        throw new Error(
            `request failed: ${response.status}`
        );
    }


    return response.json();
}


function formatSeason(value) {
    return `${value}/${String(
        value + 1
    ).slice(-2)}`;
}


function getInitials(name) {
    const words =
        name
            .trim()
            .split(/\s+/);


    if (
        words.length === 1
    ) {
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


function createPlayerPhoto(player) {
    const wrapper =
        document.createElement(
            "div"
        );


    wrapper.className =
        "players-card-photo-wrapper";


    const fallback =
        document.createElement(
            "div"
        );


    fallback.className =
        "players-card-photo-fallback";


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
        "players-card-photo";


    image.src =
        player.photo_url;


    image.alt =
        player.player_name;


    image.loading =
        "lazy";


    image.addEventListener(
        "load",
        () => {
            fallback.style.display =
                "none";
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


function createPlayerCard(player) {
    const card =
        document.createElement(
            "a"
        );


    card.className =
        "players-card";


    card.href =
        `/players/${player.player_id}?season=${season}`;


    const top =
        document.createElement(
            "div"
        );


    top.className =
        "players-card-top";


    const photo =
        createPlayerPhoto(
            player
        );


    const identity =
        document.createElement(
            "div"
        );


    identity.className =
        "players-card-identity";


    const name =
        document.createElement(
            "h2"
        );


    name.textContent =
        player.player_name;


    const team =
        document.createElement(
            "div"
        );


    team.className =
        "players-card-team";


    team.textContent =
        player.teams
        || "Unknown team";


    const position =
        document.createElement(
            "div"
        );


    position.className =
        "players-card-position";


    position.textContent =
        [
            player.position,
            player.nationality
        ]
            .filter(Boolean)
            .join(" · ");


    identity.appendChild(
        name
    );


    identity.appendChild(
        team
    );


    identity.appendChild(
        position
    );


    top.appendChild(
        photo
    );


    top.appendChild(
        identity
    );


    const statistics =
        document.createElement(
            "div"
        );


    statistics.className =
        "players-card-stats";


    statistics.innerHTML = `
        <div class="players-card-stat">

            <span>
                Apps
            </span>

            <strong>
                ${player.appearances ?? "-"}
            </strong>

        </div>

        <div class="players-card-stat">

            <span>
                Minutes
            </span>

            <strong>
                ${player.minutes ?? "-"}
            </strong>

        </div>

        <div class="players-card-stat">

            <span>
                Goals
            </span>

            <strong>
                ${player.goals ?? "-"}
            </strong>

        </div>

        <div class="players-card-stat">

            <span>
                Assists
            </span>

            <strong>
                ${player.assists ?? "-"}
            </strong>

        </div>
    `;


    card.appendChild(
        top
    );


    card.appendChild(
        statistics
    );


    return card;
}


function renderPlayers(players) {
    playersGrid.innerHTML =
        "";


    if (
        players.length === 0
    ) {
        playersGrid.innerHTML = `
            <div class="players-empty">
                No players found.
            </div>
        `;

        return;
    }


    for (
        const player
        of players
    ) {
        playersGrid.appendChild(
            createPlayerCard(
                player
            )
        );
    }
}


async function loadPlayers(
    search = ""
) {
    try {
        resultCount.textContent =
            "Loading players...";


        const params =
            new URLSearchParams();


        params.set(
            "season",
            season
        );


        params.set(
            "limit",
            100
        );


        if (
            search.trim()
        ) {
            params.set(
                "search",
                search.trim()
            );
        }


        const data =
            await fetchJSON(
                `/api/players?${params.toString()}`
            );


        renderPlayers(
            data.players
        );


        if (
            search.trim()
        ) {
            resultCount.textContent =
                `${data.count} results for "${search.trim()}"`;
        } else {
            resultCount.textContent =
                `${data.count} players`;
        }

    } catch (error) {
        console.error(
            error
        );


        resultCount.textContent =
            "Could not load players";


        playersGrid.innerHTML = `
            <div class="players-error">
                Could not load player data.
            </div>
        `;
    }
}


function handleSearch() {
    clearTimeout(
        searchTimeout
    );


    searchTimeout =
        setTimeout(
            () => {
                loadPlayers(
                    searchInput.value
                );
            },
            250
        );
}


searchInput.addEventListener(
    "input",
    handleSearch
);


seasonLabel.textContent =
    `Premier League ${formatSeason(
        season
    )}`;


loadPlayers();
