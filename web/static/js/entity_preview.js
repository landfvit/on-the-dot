const ENTITY_PREVIEW_OPEN_DELAY =
    400;

const ENTITY_PREVIEW_CLOSE_DELAY =
    220;

const ENTITY_PREVIEW_BRANDING_URL =
    "/api/branding";


let entityPreviewOpenTimer =
    null;

let entityPreviewCloseTimer =
    null;

let entityPreviewCurrentTrigger =
    null;

let entityPreviewCurrentEntity =
    null;

let entityPreviewBranding =
    null;


const entityPreviewCache =
    new Map();


function isDesktopHover() {
    return window.matchMedia(
        "(hover: hover) and (pointer: fine)"
    ).matches;
}


function ensureEntityPreviewStyles() {
    const existing =
        document.querySelector(
            'link[href*="entity_preview.css"]'
        );


    if (existing) {
        return;
    }


    const link =
        document.createElement(
            "link"
        );


    link.rel =
        "stylesheet";


    link.href =
        "/assets/css/entity_preview.css?v=4";


    document.head.appendChild(
        link
    );
}


function createPreviewLayer() {
    let layer =
        document.querySelector(
            ".entity-preview-layer"
        );


    if (layer) {
        return layer;
    }


    layer =
        document.createElement(
            "div"
        );


    layer.className =
        "entity-preview-layer";


    const card =
        document.createElement(
            "div"
        );


    card.className =
        "entity-preview-card";


    layer.appendChild(
        card
    );


    card.addEventListener(
        "mouseenter",
        () => {
            cancelEntityPreviewClose();
        }
    );


    card.addEventListener(
        "mouseleave",
        () => {
            scheduleEntityPreviewClose();
        }
    );


    document.body.appendChild(
        layer
    );


    return layer;
}


const entityPreviewLayer =
    createPreviewLayer();


const entityPreviewCard =
    entityPreviewLayer.querySelector(
        ".entity-preview-card"
    );


async function loadPreviewBranding() {
    if (entityPreviewBranding) {
        return entityPreviewBranding;
    }


    if (window.entityBrandingData) {
        entityPreviewBranding =
            window.entityBrandingData;

        return entityPreviewBranding;
    }


    try {
        const response =
            await fetch(
                ENTITY_PREVIEW_BRANDING_URL
            );


        if (!response.ok) {
            return null;
        }


        entityPreviewBranding =
            await response.json();


        return entityPreviewBranding;

    } catch (error) {
        return null;
    }
}


function getPreviewTeamBranding(
    teamId
) {
    return (
        entityPreviewBranding
        ?.sports
        ?.football
        ?.teams
        ?.[String(teamId)]
        || null
    );
}


function findEntityTrigger(target) {
    if (
        !(target instanceof Element)
    ) {
        return null;
    }


    if (
        target.closest(
            '#global-search-overlay, [data-entity-preview="disabled"]'
        )
    ) {
        return null;
    }


    if (
        target.closest(
            ".entity-preview-card"
        )
    ) {
        return null;
    }


    return target.closest(
        [
            "[data-entity-type][data-entity-id]",
            'a[href^="/teams/"]',
            'a[href^="/players/"]'
        ].join(",")
    );
}


function parseEntityFromTrigger(
    trigger
) {
    if (!trigger) {
        return null;
    }


    const dataType =
        trigger.dataset.entityType;


    const dataId =
        trigger.dataset.entityId;


    const season =
        Number(
            trigger.dataset.season
            || new URL(
                trigger.href
                || window.location.href,
                window.location.origin
            ).searchParams.get(
                "season"
            )
            || 2024
        );


    if (
        dataType
        && dataId
    ) {
        return {
            type: dataType,
            id: Number(
                dataId
            ),
            season
        };
    }


    if (
        trigger.tagName !== "A"
    ) {
        return null;
    }


    try {
        const url =
            new URL(
                trigger.href,
                window.location.origin
            );


        const teamMatch =
            url.pathname.match(
                /^\/teams\/(\d+)/
            );


        if (teamMatch) {
            return {
                type: "team",
                id: Number(
                    teamMatch[1]
                ),
                season
            };
        }


        const playerMatch =
            url.pathname.match(
                /^\/players\/(\d+)/
            );


        if (playerMatch) {
            return {
                type: "player",
                id: Number(
                    playerMatch[1]
                ),
                season
            };
        }

    } catch (error) {
        return null;
    }


    return null;
}


function getEntityCacheKey(
    entity
) {
    return [
        entity.type,
        entity.id,
        entity.season
    ].join(":");
}


function cancelEntityPreviewOpen() {
    if (
        entityPreviewOpenTimer
        !== null
    ) {
        window.clearTimeout(
            entityPreviewOpenTimer
        );


        entityPreviewOpenTimer =
            null;
    }
}


function cancelEntityPreviewClose() {
    if (
        entityPreviewCloseTimer
        !== null
    ) {
        window.clearTimeout(
            entityPreviewCloseTimer
        );


        entityPreviewCloseTimer =
            null;
    }
}


function closeEntityPreview() {
    cancelEntityPreviewOpen();

    cancelEntityPreviewClose();


    entityPreviewLayer.classList.remove(
        "is-open"
    );


    entityPreviewCurrentTrigger =
        null;


    entityPreviewCurrentEntity =
        null;
}


function scheduleEntityPreviewClose() {
    cancelEntityPreviewClose();


    entityPreviewCloseTimer =
        window.setTimeout(
            () => {
                closeEntityPreview();
            },
            ENTITY_PREVIEW_CLOSE_DELAY
        );
}


function scheduleEntityPreviewOpen(
    trigger,
    entity
) {
    cancelEntityPreviewOpen();

    cancelEntityPreviewClose();


    entityPreviewOpenTimer =
        window.setTimeout(
            () => {
                openEntityPreview(
                    trigger,
                    entity
                );
            },
            ENTITY_PREVIEW_OPEN_DELAY
        );
}


function renderPreviewLoading() {
    entityPreviewCard.innerHTML = `
        <div class="entity-preview-loading">
            Loading...
        </div>
    `;
}


function createPreviewLogo(
    logoUrl,
    name
) {
    if (!logoUrl) {
        const fallback =
            document.createElement(
                "div"
            );


        fallback.className =
            "entity-preview-logo-fallback";


        fallback.textContent =
            name
                ?.slice(
                    0,
                    2
                )
                .toUpperCase()
            || "?";


        return fallback;
    }


    const wrapper =
        document.createElement(
            "div"
        );


    wrapper.className =
        "entity-preview-logo";


    const image =
        document.createElement(
            "img"
        );


    image.src =
        logoUrl;


    image.alt =
        name;


    image.loading =
        "lazy";


    image.addEventListener(
        "error",
        () => {
            wrapper.innerHTML =
                "";


            const fallback =
                document.createElement(
                    "span"
                );


            fallback.className =
                "entity-preview-logo-fallback";


            fallback.textContent =
                name
                    ?.slice(
                        0,
                        2
                    )
                    .toUpperCase()
                || "?";


            wrapper.appendChild(
                fallback
            );
        }
    );


    wrapper.appendChild(
        image
    );


    return wrapper;
}


function renderTeamPreview(
    data,
    entity
) {
    const team =
        data.team;


    const branding =
        getPreviewTeamBranding(
            entity.id
        );


    entityPreviewCard.innerHTML =
        "";


    const header =
        document.createElement(
            "div"
        );


    header.className =
        "entity-preview-header";


    header.appendChild(
        createPreviewLogo(
            branding?.logo_url,
            team.team_name
        )
    );


    const identity =
        document.createElement(
            "div"
        );


    identity.className =
        "entity-preview-identity";


    identity.innerHTML = `
        <span class="entity-preview-eyebrow">
            Football · Team
        </span>

        <h3>
            ${team.team_name}
        </h3>

        <p>
            Premier League
            ·
            ${entity.season}/${String(
                entity.season + 1
            ).slice(-2)}
        </p>
    `;


    header.appendChild(
        identity
    );


    const statistics =
        document.createElement(
            "div"
        );


    statistics.className =
        "entity-preview-stats";


    statistics.innerHTML = `
        <div>
            <span>Position</span>
            <strong>
                #${team.league_position ?? "-"}
            </strong>
        </div>

        <div>
            <span>Points</span>
            <strong>
                ${team.points ?? "-"}
            </strong>
        </div>

        <div>
            <span>Played</span>
            <strong>
                ${team.matches_played ?? "-"}
            </strong>
        </div>

        <div>
            <span>Record</span>
            <strong>
                ${team.wins ?? 0}-${team.draws ?? 0}-${team.losses ?? 0}
            </strong>
        </div>
    `;


    const footer =
        document.createElement(
            "div"
        );


    footer.className =
        "entity-preview-footer";


    const link =
        document.createElement(
            "a"
        );


    link.href =
        `/teams/${entity.id}?season=${entity.season}`;


    link.textContent =
        "Open team profile →";


    footer.appendChild(
        link
    );


    entityPreviewCard.appendChild(
        header
    );


    entityPreviewCard.appendChild(
        statistics
    );


    entityPreviewCard.appendChild(
        footer
    );
}


function renderPlayerPreview(
    data,
    entity
) {
    const player =
        data.player;


    const summary =
        data.summary || {};


    const teamRecords =
        Array.isArray(
            data.statistics
        )
            ? data.statistics
            : [];


    entityPreviewCard.innerHTML =
        "";


    const header =
        document.createElement(
            "div"
        );


    header.className =
        "entity-preview-header";


    const imageWrapper =
        document.createElement(
            "div"
        );


    imageWrapper.className =
        "entity-preview-player-photo";


    if (player.photo_url) {
        const image =
            document.createElement(
                "img"
            );


        image.src =
            player.photo_url;


        image.alt =
            player.player_name;


        image.loading =
            "lazy";


        imageWrapper.appendChild(
            image
        );

    } else {
        imageWrapper.textContent =
            player.player_name
                ?.slice(
                    0,
                    2
                )
                .toUpperCase()
            || "?";
    }


    const identity =
        document.createElement(
            "div"
        );


    identity.className =
        "entity-preview-identity";


    identity.innerHTML = `
        <span class="entity-preview-eyebrow">
            Football · Athlete
        </span>

        <h3>
            ${player.player_name}
        </h3>

        <p>
            ${player.nationality || "Unknown nationality"}
        </p>
    `;


    header.appendChild(
        imageWrapper
    );


    header.appendChild(
        identity
    );


    const teams =
        document.createElement(
            "div"
        );


    teams.className =
        "entity-preview-team-list";


    const seenTeams =
        new Set();


    for (
        const record
        of teamRecords
    ) {
        if (
            seenTeams.has(
                record.team_id
            )
        ) {
            continue;
        }


        seenTeams.add(
            record.team_id
        );


        const branding =
            getPreviewTeamBranding(
                record.team_id
            );


        const team =
            document.createElement(
                "div"
            );


        team.className =
            "entity-preview-team";


        if (
            branding?.logo_url
        ) {
            const logo =
                document.createElement(
                    "img"
                );


            logo.src =
                branding.logo_url;


            logo.alt =
                record.team_name;


            team.appendChild(
                logo
            );
        }


        const name =
            document.createElement(
                "span"
            );


        name.textContent =
            record.team_name;


        team.appendChild(
            name
        );


        teams.appendChild(
            team
        );
    }


    const statistics =
        document.createElement(
            "div"
        );


    statistics.className =
        "entity-preview-stats";


    statistics.innerHTML = `
        <div>
            <span>Apps</span>
            <strong>
                ${summary.appearances ?? 0}
            </strong>
        </div>

        <div>
            <span>Minutes</span>
            <strong>
                ${summary.minutes ?? 0}
            </strong>
        </div>

        <div>
            <span>Goals</span>
            <strong>
                ${summary.goals ?? 0}
            </strong>
        </div>

        <div>
            <span>Assists</span>
            <strong>
                ${summary.assists ?? 0}
            </strong>
        </div>
    `;


    const footer =
        document.createElement(
            "div"
        );


    footer.className =
        "entity-preview-footer";


    const link =
        document.createElement(
            "a"
        );


    link.href =
        `/players/${entity.id}?season=${entity.season}`;


    link.textContent =
        "Open player profile →";


    footer.appendChild(
        link
    );


    entityPreviewCard.appendChild(
        header
    );


    if (
        teams.children.length > 0
    ) {
        entityPreviewCard.appendChild(
            teams
        );
    }


    entityPreviewCard.appendChild(
        statistics
    );


    entityPreviewCard.appendChild(
        footer
    );
}


function renderPreviewError() {
    entityPreviewCard.innerHTML = `
        <div class="entity-preview-error">
            Preview could not be loaded.
        </div>
    `;
}


async function fetchEntityData(
    entity
) {
    const cacheKey =
        getEntityCacheKey(
            entity
        );


    if (
        entityPreviewCache.has(
            cacheKey
        )
    ) {
        return entityPreviewCache.get(
            cacheKey
        );
    }


    let url = null;


    if (
        entity.type === "team"
    ) {
        url =
            `/api/teams/${entity.id}?season=${entity.season}`;
    }


    if (
        entity.type === "player"
        || entity.type === "athlete"
    ) {
        url =
            `/api/players/${entity.id}?season=${entity.season}`;
    }


    if (!url) {
        throw new Error(
            "unsupported entity"
        );
    }


    const response =
        await fetch(
            url
        );


    if (!response.ok) {
        throw new Error(
            `preview request failed: ${response.status}`
        );
    }


    const data =
        await response.json();


    entityPreviewCache.set(
        cacheKey,
        data
    );


    return data;
}


function positionPreview(
    trigger
) {
    const triggerRect =
        trigger.getBoundingClientRect();


    const cardRect =
        entityPreviewCard.getBoundingClientRect();


    const margin = 12;

    const viewportPadding = 12;


    let left =
        triggerRect.right
        + margin;


    if (
        left
        + cardRect.width
        > window.innerWidth
        - viewportPadding
    ) {
        left =
            triggerRect.left
            - cardRect.width
            - margin;
    }


    if (
        left < viewportPadding
    ) {
        left =
            viewportPadding;
    }


    let top =
        triggerRect.top;


    if (
        top
        + cardRect.height
        > window.innerHeight
        - viewportPadding
    ) {
        top =
            window.innerHeight
            - cardRect.height
            - viewportPadding;
    }


    if (
        top < viewportPadding
    ) {
        top =
            viewportPadding;
    }


    entityPreviewCard.style.left =
        `${Math.round(left)}px`;


    entityPreviewCard.style.top =
        `${Math.round(top)}px`;
}


async function openEntityPreview(
    trigger,
    entity
) {
    if (!isDesktopHover()) {
        return;
    }


    if (
        trigger.closest(
            "#global-search-overlay"
        )
    ) {
        return;
    }


    entityPreviewCurrentTrigger =
        trigger;


    entityPreviewCurrentEntity =
        entity;


    renderPreviewLoading();


    entityPreviewLayer.classList.add(
        "is-open"
    );


    positionPreview(
        trigger
    );


    try {
        await loadPreviewBranding();


        const data =
            await fetchEntityData(
                entity
            );


        if (
            entityPreviewCurrentTrigger
            !== trigger
        ) {
            return;
        }


        if (
            entity.type === "team"
        ) {
            renderTeamPreview(
                data,
                entity
            );

        } else {
            renderPlayerPreview(
                data,
                entity
            );
        }


        positionPreview(
            trigger
        );

    } catch (error) {
        console.error(
            error
        );


        renderPreviewError();


        positionPreview(
            trigger
        );
    }
}


document.addEventListener(
    "mouseover",
    event => {
        if (!isDesktopHover()) {
            return;
        }


        const trigger =
            findEntityTrigger(
                event.target
            );


        if (!trigger) {
            return;
        }


        const related =
            event.relatedTarget;


        if (
            related instanceof Node
            && trigger.contains(
                related
            )
        ) {
            return;
        }


        const entity =
            parseEntityFromTrigger(
                trigger
            );


        if (!entity) {
            return;
        }


        scheduleEntityPreviewOpen(
            trigger,
            entity
        );
    }
);


document.addEventListener(
    "mouseout",
    event => {
        if (!isDesktopHover()) {
            return;
        }


        const trigger =
            findEntityTrigger(
                event.target
            );


        if (!trigger) {
            return;
        }


        const related =
            event.relatedTarget;


        if (
            related instanceof Node
            && trigger.contains(
                related
            )
        ) {
            return;
        }


        scheduleEntityPreviewClose();
    }
);


document.addEventListener(
    "click",
    event => {
        const trigger =
            findEntityTrigger(
                event.target
            );


        if (!trigger) {
            return;
        }


        const entity =
            parseEntityFromTrigger(
                trigger
            );


        if (!entity) {
            return;
        }


        closeEntityPreview();


        if (
            trigger.tagName === "A"
        ) {
            return;
        }


        event.preventDefault();


        if (
            entity.type === "team"
        ) {
            window.location.href =
                `/teams/${entity.id}?season=${entity.season}`;

            return;
        }


        window.location.href =
            `/players/${entity.id}?season=${entity.season}`;
    }
);


document.addEventListener(
    "keydown",
    event => {
        if (
            event.key === "Escape"
        ) {
            closeEntityPreview();
        }
    }
);


window.addEventListener(
    "scroll",
    () => {
        if (
            entityPreviewCurrentTrigger
            && entityPreviewLayer.classList.contains(
                "is-open"
            )
        ) {
            positionPreview(
                entityPreviewCurrentTrigger
            );
        }
    },
    {
        passive: true
    }
);


window.addEventListener(
    "resize",
    () => {
        if (
            !isDesktopHover()
        ) {
            closeEntityPreview();

            return;
        }


        if (
            entityPreviewCurrentTrigger
            && entityPreviewLayer.classList.contains(
                "is-open"
            )
        ) {
            positionPreview(
                entityPreviewCurrentTrigger
            );
        }
    }
);


ensureEntityPreviewStyles();
