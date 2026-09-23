import requests
import mwparserfromhell


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def get_wikitext(page_name):
    """
    Download raw wikitext of a Wikipedia page.
    """

    params = {
        "action": "parse",
        "page": page_name,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }

    response = requests.get(
        WIKIPEDIA_API,
        params=params,
        timeout=20,
        headers={
            "User-Agent": "FootballKitProject/1.0"
        }
    )

    response.raise_for_status()

    data = response.json()

    if "error" in data:
        raise ValueError(
            f"Wikipedia error: {data['error']}"
        )

    return data["parse"]["wikitext"]


def clean_value(value):
    """
    Convert mwparser value into a normal string.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def get_parameter(template, name):
    """
    Safely read a parameter from a MediaWiki template.
    """

    if template.has(name):
        return clean_value(
            template.get(name).value
        )

    return None


def extract_kit(template, number):
    """
    Extract one kit.

    number:
        1 = home
        2 = away
        3 = third
    """

    return {
        "left_arm": {
            "color": get_parameter(
                template,
                f"leftarm{number}"
            ),
            "pattern": get_parameter(
                template,
                f"pattern_la{number}"
            ),
        },

        "body": {
            "color": get_parameter(
                template,
                f"body{number}"
            ),
            "pattern": get_parameter(
                template,
                f"pattern_b{number}"
            ),
        },

        "right_arm": {
            "color": get_parameter(
                template,
                f"rightarm{number}"
            ),
            "pattern": get_parameter(
                template,
                f"pattern_ra{number}"
            ),
        },

        "shorts": {
            "color": get_parameter(
                template,
                f"shorts{number}"
            ),
            "pattern": get_parameter(
                template,
                f"pattern_sh{number}"
            ),
        },

        "socks": {
            "color": get_parameter(
                template,
                f"socks{number}"
            ),
            "pattern": get_parameter(
                template,
                f"pattern_so{number}"
            ),
        },
    }


def find_team_infobox(wikitext):
    """
    Find the football club infobox.
    """

    code = mwparserfromhell.parse(wikitext)

    templates = code.filter_templates(
        recursive=True
    )

    for template in templates:

        name = str(template.name).strip().lower()

        if "infobox football club" in name:
            return template

    raise ValueError(
        "Football club infobox was not found."
    )


def import_team(page_name):
    """
    Import Home / Away / Third kits from Wikipedia.
    """

    print(
        f"Downloading Wikipedia page: {page_name}"
    )

    wikitext = get_wikitext(page_name)

    infobox = find_team_infobox(wikitext)

    result = {
        "team": page_name,

        "home": extract_kit(
            infobox,
            1
        ),

        "away": extract_kit(
            infobox,
            2
        ),

        "third": extract_kit(
            infobox,
            3
        ),
    }

    return result