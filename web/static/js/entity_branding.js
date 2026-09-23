const ENTITY_BRANDING_URL =
    "/assets/data/entity_branding.json?v=2";


let entityBrandingData = null;

let entityBrandingScanScheduled =
    false;


function ensureEntityBrandingStyles() {
    const existing =
        document.querySelector(
            'link[href*="entity_branding.css"]'
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
        "/assets/css/entity_branding.css?v=2";


    document.head.appendChild(
        link
    );
}


function getFootballBranding() {
    return (
        entityBrandingData
        ?.sports
        ?.football
        || null
    );
}


function getTeamBranding(teamId) {
    const football =
        getFootballBranding();


    if (!football) {
        return null;
    }


    return (
        football.teams[
            String(
                teamId
            )
        ]
        || null
    );
}


function getCompetitionBranding(
    competitionId
) {
    const football =
        getFootballBranding();


    if (!football) {
        return null;
    }


    return (
        football.competitions[
            String(
                competitionId
            )
        ]
        || null
    );
}


function extractTeamId(link) {
    try {
        const url =
            new URL(
                link.href,
                window.location.origin
            );


        const match =
            url.pathname.match(
                /^\/teams\/(\d+)/
            );


        if (!match) {
            return null;
        }


        return Number(
            match[1]
        );

    } catch (error) {
        return null;
    }
}


function createLogo(
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


    image.className =
        className;


    image.loading =
        "lazy";


    image.addEventListener(
        "error",
        () => {
            image.remove();
        }
    );


    return image;
}


function hasBrandingLogo(
    element
) {
    return Boolean(
        element.querySelector(
            [
                ".entity-branding-large-logo",
                ".entity-branding-card-logo",
                ".entity-branding-competition-logo"
            ].join(",")
        )
    );
}


function replaceBadgeWithLogo(
    badge,
    branding,
    className
) {
    if (
        !badge
        || !branding
        || !branding.logo_url
    ) {
        return;
    }


    /*
    another script can replace the badge content later.
    only skip if our logo is actually still inside.
    */
    if (
        badge.dataset.brandingApplied
        === "true"
        && hasBrandingLogo(
            badge
        )
    ) {
        return;
    }


    badge.dataset.brandingApplied =
        "true";


    badge.classList.add(
        "entity-branding-image-mode"
    );


    badge.innerHTML =
        "";


    badge.appendChild(
        createLogo(
            branding.logo_url,
            branding.name,
            className
        )
    );
}


function decorateTeamCard(
    link,
    branding
) {
    const badge =
        link.querySelector(
            [
                ".team-card-badge",
                ".competition-team-card-badge"
            ].join(",")
        );


    if (!badge) {
        return false;
    }


    replaceBadgeWithLogo(
        badge,
        branding,
        "entity-branding-card-logo"
    );


    return true;
}


function decorateRegularTeamLink(
    link,
    branding
) {
    if (
        !branding.logo_url
    ) {
        return;
    }


    const existingLogo =
        link.querySelector(
            ":scope > .entity-team-logo-inline"
        );


    if (existingLogo) {
        return;
    }


    link.dataset.brandingApplied =
        "true";


    link.classList.add(
        "entity-branding-link"
    );


    const logo =
        createLogo(
            branding.logo_url,
            branding.name,
            "entity-team-logo-inline"
        );


    link.prepend(
        logo
    );
}


function decorateTeamLink(link) {
    /*
    search already has its own rich result design
    */
    if (
        link.closest(
            "#global-search-overlay"
        )
    ) {
        return;
    }


    const teamId =
        extractTeamId(
            link
        );


    if (teamId === null) {
        return;
    }


    const branding =
        getTeamBranding(
            teamId
        );


    if (
        !branding
        || !branding.logo_url
    ) {
        return;
    }


    if (
        decorateTeamCard(
            link,
            branding
        )
    ) {
        return;
    }


    decorateRegularTeamLink(
        link,
        branding
    );
}


function decorateTeamPageHeader() {
    const page =
        document.getElementById(
            "team-page"
        );


    if (!page) {
        return;
    }


    const teamId =
        Number(
            page.dataset.teamId
        );


    if (!teamId) {
        return;
    }


    const branding =
        getTeamBranding(
            teamId
        );


    if (!branding) {
        return;
    }


    const badge =
        document.getElementById(
            "team-badge"
        );


    replaceBadgeWithLogo(
        badge,
        branding,
        "entity-branding-large-logo"
    );
}


function decorateCompetitionPageHeader() {
    const page =
        document.getElementById(
            "competition-page"
        );


    if (!page) {
        return;
    }


    const competitionId =
        Number(
            page.dataset.leagueId
        );


    if (!competitionId) {
        return;
    }


    const branding =
        getCompetitionBranding(
            competitionId
        );


    if (!branding) {
        return;
    }


    const badge =
        document.getElementById(
            "competition-badge"
        );


    replaceBadgeWithLogo(
        badge,
        branding,
        "entity-branding-competition-logo"
    );
}


function decorateHomepageCompetitions() {
    const branding =
        getCompetitionBranding(
            39
        );


    if (!branding) {
        return;
    }


    const badges =
        document.querySelectorAll(
            [
                ".home-featured-badge",
                ".home-competition-badge"
            ].join(",")
        );


    for (
        const badge
        of badges
    ) {
        replaceBadgeWithLogo(
            badge,
            branding,
            "entity-branding-competition-logo"
        );
    }
}


function scanEntityBranding() {
    if (!entityBrandingData) {
        return;
    }


    const teamLinks =
        document.querySelectorAll(
            'a[href^="/teams/"]'
        );


    for (
        const link
        of teamLinks
    ) {
        decorateTeamLink(
            link
        );
    }


    decorateTeamPageHeader();

    decorateCompetitionPageHeader();

    decorateHomepageCompetitions();
}


function scheduleEntityBrandingScan() {
    if (
        entityBrandingScanScheduled
    ) {
        return;
    }


    entityBrandingScanScheduled =
        true;


    window.requestAnimationFrame(
        () => {
            entityBrandingScanScheduled =
                false;


            scanEntityBranding();
        }
    );
}


function startEntityBrandingObserver() {
    const observer =
        new MutationObserver(
            mutations => {
                let shouldScan =
                    false;


                for (
                    const mutation
                    of mutations
                ) {
                    if (
                        mutation.type
                        === "childList"
                        && (
                            mutation.addedNodes.length
                            > 0
                            || mutation.removedNodes.length
                            > 0
                        )
                    ) {
                        shouldScan =
                            true;

                        break;
                    }
                }


                if (shouldScan) {
                    scheduleEntityBrandingScan();
                }
            }
        );


    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );
}


async function loadEntityBranding() {
    try {
        const response =
            await fetch(
                ENTITY_BRANDING_URL
            );


        if (!response.ok) {
            throw new Error(
                `branding request failed: ${response.status}`
            );
        }


        entityBrandingData =
            await response.json();


        /*
        expose branding for other global components
        */
        window.entityBrandingData =
            entityBrandingData;


        window.getTeamBranding =
            getTeamBranding;


        window.getCompetitionBranding =
            getCompetitionBranding;


        scanEntityBranding();


        startEntityBrandingObserver();

    } catch (error) {
        console.error(
            "entity branding:",
            error
        );
    }
}


ensureEntityBrandingStyles();

loadEntityBranding();