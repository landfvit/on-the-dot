(function () {
const globalSearchButton =
    document.getElementById(
        "global-search-button"
    );


const globalSearchOverlay =
    document.getElementById(
        "global-search-overlay"
    );


const globalSearchInput =
    document.getElementById(
        "global-search-input"
    );


const globalSearchContent =
    document.getElementById(
        "global-search-content"
    );


const globalSearchClose =
    document.getElementById(
        "global-search-close"
    );


let searchTimer = null;

let searchController = null;

let selectedResultIndex = -1;

let resultElements = [];


const sportIcons = {
    football: "⚽",
    formula1: "F1",
    hockey: "🏒",
    tennis: "🎾",
    cycling: "🚴"
};


const groupSettings = [
    {
        key: "athletes",
        title: "Athletes"
    },
    {
        key: "teams",
        title: "Teams"
    },
    {
        key: "competitions",
        title: "Competitions"
    }
];


function getInitials(name) {
    if (!name) {
        return "?";
    }


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


function getTypeLabel(type) {
    if (type === "athlete") {
        return "Athlete";
    }


    if (type === "team") {
        return "Team";
    }


    if (type === "competition") {
        return "Competition";
    }


    return type;
}


function getSportIcon(sport) {
    return (
        sportIcons[sport]
        || "●"
    );
}


function suppressEntityPreview() {
    const layer =
        document.querySelector(
            ".entity-preview-layer"
        );


    if (!layer) {
        return;
    }


    layer.classList.remove(
        "is-open"
    );


    layer.style.display =
        "none";


    layer.dataset.searchSuppressed =
        "true";
}


function restoreEntityPreview() {
    const layer =
        document.querySelector(
            ".entity-preview-layer"
        );


    if (!layer) {
        return;
    }


    if (
        layer.dataset.searchSuppressed
        !== "true"
    ) {
        return;
    }


    layer.style.removeProperty(
        "display"
    );


    delete layer.dataset.searchSuppressed;
}


function openSearch() {
    suppressEntityPreview();
    if (!globalSearchOverlay.open) globalSearchOverlay.showModal();
    runSearch(globalSearchInput.value.trim());


    globalSearchOverlay.classList.add(
        "is-open"
    );


    globalSearchOverlay.setAttribute(
        "aria-hidden",
        "false"
    );


    document.body.classList.add(
        "search-open"
    );


    globalSearchInput.focus();
    globalSearchInput.select();
}


function closeSearch() {
    window.clearTimeout(searchTimer);
    globalSearchOverlay.close();
    globalSearchOverlay.classList.remove(
        "is-open"
    );


    globalSearchOverlay.setAttribute(
        "aria-hidden",
        "true"
    );


    document.body.classList.remove(
        "search-open"
    );


    selectedResultIndex = -1;


    if (searchController) {
        searchController.abort();

        searchController = null;
    }


    restoreEntityPreview();
}


function createImage(result) {
    const wrapper =
        document.createElement(
            "div"
        );


    wrapper.className =
        `global-search-image ${result.type}`;


    const fallback =
        document.createElement(
            "span"
        );


    fallback.className =
        "global-search-image-fallback";


    fallback.textContent =
        getInitials(
            result.name
        );


    wrapper.appendChild(
        fallback
    );


    if (!result.image_url) {
        return wrapper;
    }


    const image =
        document.createElement(
            "img"
        );


    image.src =
        result.image_url;


    image.alt =
        result.name;


    image.loading =
        "lazy";


    image.addEventListener(
        "load",
        () => {
            fallback.remove();
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


function createMeta(result) {
    const meta =
        document.createElement(
            "div"
        );


    meta.className =
        "global-search-meta";


    if (result.flag_url) {
        const flag =
            document.createElement(
                "img"
            );


        flag.className =
            "global-search-flag";


        flag.src =
            result.flag_url;


        flag.alt =
            result.country_name
            || "Country flag";


        flag.loading =
            "lazy";


        meta.appendChild(
            flag
        );
    }


    if (result.country_name) {
        const country =
            document.createElement(
                "span"
            );


        country.textContent =
            result.country_name;


        meta.appendChild(
            country
        );
    }


    if (
        result.country_name
        && result.sport_name
    ) {
        const dot =
            document.createElement(
                "span"
            );


        dot.className =
            "global-search-dot";


        dot.textContent =
            "·";


        meta.appendChild(
            dot
        );
    }


    if (result.sport_name) {
        const sport =
            document.createElement(
                "span"
            );


        sport.className =
            "global-search-sport";


        sport.textContent =
            `${getSportIcon(
                result.sport
            )} ${result.sport_name}`;


        meta.appendChild(
            sport
        );
    }


    return meta;
}


function createTeams(teams) {
    const container =
        document.createElement(
            "div"
        );


    container.className =
        "global-search-teams";


    for (
        const team
        of teams
    ) {
        const chip =
            document.createElement(
                "span"
            );


        chip.className =
            "global-search-team-chip";


        if (team.logo_url) {
            const logo =
                document.createElement(
                    "img"
                );


            logo.className =
                "global-search-team-logo";


            logo.src =
                team.logo_url;


            logo.alt =
                team.team_name;


            logo.loading =
                "lazy";


            chip.appendChild(
                logo
            );
        }


        const name =
            document.createElement(
                "span"
            );


        name.textContent =
            team.team_name;


        chip.appendChild(
            name
        );


        container.appendChild(
            chip
        );
    }


    return container;
}


function createResult(result) {
    const link =
        document.createElement(
            "a"
        );


    link.className =
        "global-search-result";


    link.href =
        result.url;


    link.dataset.searchResult =
        "true";


    const image =
        createImage(
            result
        );


    const content =
        document.createElement(
            "div"
        );


    content.className =
        "global-search-result-content";


    const nameRow =
        document.createElement(
            "div"
        );


    nameRow.className =
        "global-search-name-row";


    const name =
        document.createElement(
            "span"
        );


    name.className =
        "global-search-name";


    name.textContent =
        result.name;


    const type =
        document.createElement(
            "span"
        );


    type.className =
        "global-search-type";


    type.textContent =
        getTypeLabel(
            result.type
        );


    nameRow.appendChild(
        name
    );


    nameRow.appendChild(
        type
    );


    content.appendChild(
        nameRow
    );


    content.appendChild(
        createMeta(
            result
        )
    );


    if (
        result.type === "athlete"
        && Array.isArray(
            result.teams
        )
        && result.teams.length > 0
    ) {
        content.appendChild(
            createTeams(
                result.teams
            )
        );
    }


    const arrow =
        document.createElement(
            "span"
        );


    arrow.className =
        "global-search-arrow";


    arrow.textContent =
        "→";


    link.appendChild(
        image
    );


    link.appendChild(
        content
    );


    link.appendChild(
        arrow
    );


    link.addEventListener(
        "mouseenter",
        () => {
            const index =
                resultElements.indexOf(
                    link
                );


            if (index !== -1) {
                setSelectedResult(
                    index
                );
            }
        }
    );


    return link;
}


function renderGroup(
    title,
    results
) {
    if (
        !results
        || results.length === 0
    ) {
        return;
    }


    const group =
        document.createElement(
            "section"
        );


    group.className =
        "global-search-group";


    const header =
        document.createElement(
            "div"
        );


    header.className =
        "global-search-group-header";


    const titleElement =
        document.createElement(
            "span"
        );


    titleElement.textContent =
        title;


    const count =
        document.createElement(
            "span"
        );


    count.className =
        "global-search-group-count";


    count.textContent =
        results.length;


    header.appendChild(
        titleElement
    );


    header.appendChild(
        count
    );


    group.appendChild(
        header
    );


    for (
        const result
        of results
    ) {
        const element =
            createResult(
                result
            );


        resultElements.push(
            element
        );


        group.appendChild(
            element
        );
    }


    globalSearchContent.appendChild(
        group
    );
}


function renderResults(data) {
    globalSearchContent.innerHTML =
        "";


    resultElements = [];

    selectedResultIndex = -1;


    if (
        !data
        || data.count === 0
    ) {
        globalSearchContent.innerHTML = `
            <div class="global-search-message">

                <p>
                    No results found for
                    <strong></strong>.
                </p>

            </div>
        `;


        const strong =
            globalSearchContent.querySelector(
                "strong"
            );


        strong.textContent =
            data?.query || "";


        return;
    }


    for (
        const group
        of groupSettings
    ) {
        renderGroup(
            group.title,
            data.groups[
                group.key
            ]
        );
    }
}


function renderLoading() {
    globalSearchContent.innerHTML = `
        <div class="global-search-message">
            <p>
                Searching...
            </p>
        </div>
    `;


    resultElements = [];

    selectedResultIndex = -1;
}


function renderStartMessage() {
    globalSearchContent.replaceChildren();


    resultElements = [];

    selectedResultIndex = -1;
}


function renderError() {
    globalSearchContent.innerHTML = `
        <div class="global-search-message">

            <p>
                Search could not be loaded.
            </p>

        </div>
    `;


    resultElements = [];

    selectedResultIndex = -1;
}


async function runSearch(query) {
    if (
        query.length < 2
    ) {
        if (searchController) {
            searchController.abort();

            searchController = null;
        }


        renderStartMessage();

        return;
    }


    if (searchController) {
        searchController.abort();
    }


    searchController =
        new AbortController();
    const controller = searchController;


    renderLoading();


    try {
        const response =
            await fetch(
                `/api/search?q=${encodeURIComponent(
                    query
                )}`,
                {
                    signal:
                        controller.signal
                }
            );


        if (!response.ok) {
            throw new Error(
                `search failed: ${response.status}`
            );
        }


        const data =
            await response.json();

        if (controller.signal.aborted || controller !== searchController) return;

        renderResults(
            data
        );


    } catch (error) {
        if (
            error.name === "AbortError" || controller.signal.aborted
        ) {
            return;
        }


        console.error(
            error
        );


        renderError();
    }
}


function scheduleSearch() {
    const query =
        globalSearchInput.value.trim();


    window.clearTimeout(
        searchTimer
    );

    if (searchController) searchController.abort();
    if (query.length < 2) {
        renderStartMessage();
        return;
    }
    renderLoading();


    searchTimer =
        window.setTimeout(
            () => {
                runSearch(
                    query
                );
            },
            180
        );
}


function setSelectedResult(index) {
    for (
        const result
        of resultElements
    ) {
        result.classList.remove(
            "is-selected"
        );
    }


    if (
        index < 0
        || index >= resultElements.length
    ) {
        selectedResultIndex = -1;

        return;
    }


    selectedResultIndex =
        index;


    const selected =
        resultElements[
            selectedResultIndex
        ];


    selected.classList.add(
        "is-selected"
    );


    selected.scrollIntoView(
        {
            block: "nearest"
        }
    );
}


function moveSelection(direction) {
    if (
        resultElements.length === 0
    ) {
        return;
    }


    let nextIndex =
        selectedResultIndex
        + direction;


    if (
        nextIndex >= resultElements.length
    ) {
        nextIndex = 0;
    }


    if (
        nextIndex < 0
    ) {
        nextIndex =
            resultElements.length
            - 1;
    }


    setSelectedResult(
        nextIndex
    );
}


function openSelectedResult() {
    if (
        selectedResultIndex < 0
        || selectedResultIndex
            >= resultElements.length
    ) {
        if (
            resultElements.length > 0
        ) {
            window.location.href =
                resultElements[0].href;
        }


        return;
    }


    window.location.href =
        resultElements[
            selectedResultIndex
        ].href;
}


globalSearchButton.addEventListener(
    "click",
    openSearch
);


globalSearchClose.addEventListener(
    "click",
    closeSearch
);

globalSearchOverlay.addEventListener("cancel", event => {
    event.preventDefault();
    closeSearch();
});


globalSearchOverlay.addEventListener(
    "click",
    event => {
        if (
            event.target
            === globalSearchOverlay
        ) {
            event.preventDefault();
            closeSearch();
        }
    }
);
/*
stop entity preview events inside search
*/
globalSearchOverlay.addEventListener(
    "mouseover",
    event => {
        event.stopPropagation();
    }
);


globalSearchOverlay.addEventListener(
    "mouseout",
    event => {
        event.stopPropagation();
    }
);


globalSearchInput.addEventListener(
    "input",
    scheduleSearch
);


globalSearchInput.addEventListener(
    "keydown",
    event => {
        if (
            event.key === "ArrowDown"
        ) {
            event.preventDefault();

            moveSelection(
                1
            );

            return;
        }


        if (
            event.key === "ArrowUp"
        ) {
            event.preventDefault();

            moveSelection(
                -1
            );

            return;
        }


        if (
            event.key === "Enter"
        ) {
            if (
                resultElements.length > 0
            ) {
                event.preventDefault();

                openSelectedResult();
            }
        }
    }
);


document.addEventListener(
    "keydown",
    event => {
        const searchShortcut =
            (
                event.metaKey
                || event.ctrlKey
            )
            && event.key.toLowerCase()
                === "k";


        if (searchShortcut) {
            event.preventDefault();


            if (
                globalSearchOverlay.classList.contains(
                    "is-open"
                )
            ) {
                closeSearch();

            } else {
                openSearch();
            }


            return;
        }


        if (
            event.key === "Escape"
            && globalSearchOverlay.classList.contains(
                "is-open"
            )
        ) {
            event.preventDefault();
            closeSearch();
        }
    }
);
})();
