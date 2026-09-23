import json
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kits.wiki_importer import import_team

from kits.commons import (
    download_kit_patterns,
    download_base_files,
)

from kits.renderer import render_kit


KITS_CODE_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = KITS_CODE_DIRECTORY.parent

DATA_DIRECTORY = PROJECT_ROOT / "data"
KIT_DATA_DIRECTORY = DATA_DIRECTORY / "kits"

KITS_DIRECTORY = KIT_DATA_DIRECTORY / "teams"
PATTERNS_DIRECTORY = KIT_DATA_DIRECTORY / "patterns"
BASE_DIRECTORY = KIT_DATA_DIRECTORY / "base"


def create_filename(team):

    return (
        team
        .lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("/", "_")
        + ".json"
    )


def save_json(data, filename):

    KITS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        KITS_DIRECTORY
        / filename
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
        )

    print()
    print(
        f"JSON saved -> {path}"
    )

    return path


def download_all_patterns(data):

    print()
    print("============================")
    print(" Downloading patterns")
    print("============================")

    for kit_type in [
        "home",
        "away",
        "third",
    ]:

        kit = data.get(
            kit_type
        )

        if not kit:
            continue

        print()
        print(
            kit_type.upper()
        )

        download_kit_patterns(
            kit_data=kit,
            output_directory=PATTERNS_DIRECTORY,
        )


def render_all_kits(data):

    print()
    print("============================")
    print(" Vector rendering")
    print("============================")
    print()

    team = data["team"]

    for kit_type in [
        "home",
        "away",
        "third",
    ]:

        kit = data.get(
            kit_type
        )

        if not kit:
            continue

        render_kit(
            team=team,
            kit_type=kit_type,
            kit_data=kit,
        )


def main():

    parser = argparse.ArgumentParser(description='Import or build sourced pixel kit illustrations')
    parser.add_argument('--season', type=int, help='Build all teams from the season-specific catalog')
    parser.add_argument('--all-seasons', action='store_true', help='Build every sourced season, newest first')
    parser.add_argument('--team-id', type=int, help='Optionally build only one catalog team')
    args = parser.parse_args()
    if args.season is not None or args.all_seasons:
        from kits.catalog import build_season, SNAPSHOT
        seasons = sorted(map(int, json.loads(SNAPSHOT.read_text())['seasons']), reverse=True) if args.all_seasons else [args.season]
        for season in seasons:
            build_season(season, args.team_id)
        return

    print()
    print("============================")
    print(" Football Kit Importer")
    print("============================")
    print()

    team = input(
        "Wikipedia team page: "
    ).strip()

    if not team:

        print(
            "No team entered."
        )

        return

    try:

        # -----------------------------
        # Wikipedia
        # -----------------------------

        data = import_team(
            team
        )

        print()
        print("Imported data:")
        print()

        print(
            json.dumps(
                data,
                indent=4,
                ensure_ascii=False,
            )
        )


        # -----------------------------
        # Save imported data
        # -----------------------------

        filename = create_filename(
            team
        )

        save_json(
            data,
            filename,
        )


        # -----------------------------
        # Wikimedia vector base
        # -----------------------------

        download_base_files(
            BASE_DIRECTORY
        )


        # -----------------------------
        # Wikimedia kit patterns
        # -----------------------------

        download_all_patterns(
            data
        )


        # -----------------------------
        # Render SVG kits
        # -----------------------------

        render_all_kits(
            data
        )


        print()
        print("============================")
        print(" DONE")
        print("============================")
        print()

    except Exception as error:

        print()
        print("============================")
        print(" ERROR")
        print("============================")
        print()

        print(error)


if __name__ == "__main__":
    main()
