"""Import sourced market-value history and season-specific kit illustrations."""
import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.database import fetch_all
from kits.commons import request_with_retry

DATA_DIR = ROOT / "data" / "enrichment"
DATASET = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
DATASET_SOURCE = "https://github.com/dcaribou/transfermarkt-datasets"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "PL-Analytics/0.1 (local football research)"


def normalize_name(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value or "").lower()
                   if c.isalnum() and not unicodedata.combining(c))


def save_data(name, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def read_csv(name):
    response = SESSION.get(f"{DATASET}/{name}.csv.gz", timeout=90)
    response.raise_for_status()
    return csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(response.content))))


def match_player(local, candidates):
    # A name alone is not enough: require DOB and an unambiguous name match.
    birthday = str(local["birth_date"] or "")[:10]
    if not birthday:
        return None
    names = {normalize_name(local["player_name"]),
             normalize_name(f"{local['first_name'] or ''} {local['last_name'] or ''}")}
    matches = [p for p in candidates.get(birthday, []) if normalize_name(p["name"]) in names]
    if not matches:
        first = normalize_name((local["first_name"] or local["player_name"] or "").split()[0])
        last = normalize_name(local["last_name"])
        matches = [p for p in candidates.get(birthday, [])
                   if last and normalize_name(p["last_name"]) == last
                   and first and normalize_name(p["first_name"]).startswith(first[0])]
    return matches[0] if len(matches) == 1 else None


def import_values():
    by_birth = defaultdict(list)
    for player in read_csv("players"):
        by_birth[player["date_of_birth"][:10]].append(player)
    local_players = fetch_all("""
        SELECT p.player_id, p.player_name, p.first_name, p.last_name, p.birth_date
        FROM players p WHERE EXISTS (
            SELECT 1 FROM player_season_statistics s
            WHERE s.player_id = p.player_id AND s.league_id = 39
        );
    """)
    matched = {}
    for local in local_players:
        player = match_player(local, by_birth)
        if player:
            matched[player["player_id"]] = (local, player)
    histories = defaultdict(dict)
    for row in read_csv("player_valuations"):
        if row["player_id"] in matched:
            day = row["date"][:10]
            value = int(row["market_value_in_eur"])
            if day <= date.today().isoformat() and value >= 0:
                histories[row["player_id"]][day] = value
    players = {}
    for transfermarkt_id, (local, player) in matched.items():
        history = [{"date": day, "value_eur": value}
                   for day, value in sorted(histories[transfermarkt_id].items())]
        if not history:
            continue
        players[str(local["player_id"])] = {
            "transfermarkt_id": int(transfermarkt_id), "name": player["name"],
            "source_url": player["url"], "history": history,
        }
    if not players:
        raise ValueError("No matched valuations; existing data has been preserved")
    save_data("market_values.json", {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Transfermarkt", "dataset_url": DATASET_SOURCE,
        "players": players,
    })
    print(f"Market values: {len(players)}/{len(local_players)} players matched by name and DOB", flush=True)


class KitParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.club = None
        self.in_heading = False
        self.in_label = False
        self.kit = None
        self.divs = []
        self.file_link = None
        self.hidden_spans = []
        self.teams = defaultdict(list)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "span":
            style = dict(part.split(":", 1) for part in attrs.get("style", "").split(";") if ":" in part)
            style = {k.strip().lower(): v.strip().lower() for k, v in style.items()}
            self.hidden_spans.append("hidden" in attrs or style.get("visibility") == "hidden"
                                     or style.get("display") == "none")
        if tag in ("h2", "h3"):
            self.club = ""
            self.in_heading = True
        if tag == "td":
            self.kit = {"label": "", "layers": []}
        if tag == "b" and self.kit is not None:
            self.in_label = True
        if tag == "div":
            style = dict(part.split(":", 1) for part in attrs.get("style", "").split(";") if ":" in part)
            self.divs.append({k.strip(): v.strip() for k, v in style.items()})
        if tag == "a":
            self.file_link = attrs.get("href", "")
        if tag == "img" and self.kit is not None:
            source = attrs.get("src", "")
            if not source.startswith("https://upload.wikimedia.org/"):
                return
            position = next((s for s in reversed(self.divs) if s.get("position") == "absolute"), None)
            if position is None:
                return
            geometry = {}
            for key in ("left", "top", "width", "height"):
                value = position.get(key, "")
                if not re.fullmatch(r"\d+(?:\.\d+)?px", value):
                    return
                geometry[key] = float(value[:-2])
            color = position.get("background-color", "")
            split = urlsplit(source)
            self.kit["layers"].append({
                **geometry, "image_url": urlunsplit((split.scheme, split.netloc, split.path, "", "")),
                "color": color if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color) else "transparent",
                "source_url": "https://commons.wikimedia.org" + self.file_link,
            })

    def handle_endtag(self, tag):
        if tag == "span" and self.hidden_spans:
            self.hidden_spans.pop()
        if tag in ("h2", "h3"):
            self.in_heading = False
        if tag == "b":
            self.in_label = False
        if tag == "div" and self.divs:
            self.divs.pop()
        if tag == "td" and self.kit is not None:
            label = self.kit["label"].strip().lower()
            if label in ("home", "away", "third") and self.kit["layers"]:
                self.kit["type"] = label
                self.teams[self.club.strip()].append(self.kit)
            self.kit = None

    def handle_data(self, data):
        if self.in_heading:
            self.club += data
        if self.in_label and self.kit is not None and not any(self.hidden_spans):
            self.kit["label"] += data


TEAM_ALIASES = {
    "Manchester United": "Manchester United", "Manchester City": "Manchester City",
    "Brighton & Hove Albion": "Brighton", "Tottenham Hotspur": "Tottenham",
    "Leeds United": "Leeds", "Newcastle United": "Newcastle",
    "Wolverhampton Wanderers": "Wolves", "West Ham United": "West Ham",
    "Sheffield United": "Sheffield Utd", "Ipswich Town": "Ipswich",
    "Leicester City": "Leicester", "Luton Town": "Luton", "Coventry City": "Coventry",
    "Hull City": "Hull City", "Cardiff City": "Cardiff", "Swansea City": "Swansea",
    "Norwich City": "Norwich", "Stoke City": "Stoke City", "Queens Park Rangers": "QPR",
    "Huddersfield Town": "Huddersfield",
    "West Bromwich Albion": "West Brom", "Bolton Wanderers": "Bolton",
    "Wigan Athletic": "Wigan", "Blackburn Rovers": "Blackburn",
}


def import_kits(seasons):
    path = DATA_DIR / "team_kits.json"
    catalog = json.loads(path.read_text()) if path.exists() else {"seasons": {}}
    for index, season in enumerate(seasons):
        teams = fetch_all("""
            SELECT t.team_id, t.team_name FROM teams t JOIN (
                SELECT home_team_id AS team_id FROM fixtures WHERE league_id=39 AND season=%s
                UNION
                SELECT away_team_id AS team_id FROM fixtures WHERE league_id=39 AND season=%s
            ) participants USING (team_id)
        """, (season, season))
        lookup = {normalize_name(t["team_name"]): t["team_id"] for t in teams}
        if index:
            time.sleep(3)
        page = f"{season}\u2013{str(season + 1)[-2:]} Premier League kits"
        response = request_with_retry("https://commons.wikimedia.org/w/api.php", params={
            "action": "parse", "page": page, "prop": "text|revid", "format": "json",
        })
        response.raise_for_status()
        data = response.json()
        if "parse" not in data:
            print(f"Kits {season}: unavailable ({data.get('error', {}).get('code')})", flush=True)
            continue
        parser = KitParser()
        parser.feed(data["parse"]["text"]["*"])
        source = f"https://commons.wikimedia.org/w/index.php?oldid={data['parse']['revid']}"
        result = {}
        for name, kits in parser.teams.items():
            team_id = lookup.get(normalize_name(name)) or lookup.get(normalize_name(TEAM_ALIASES.get(name, name)))
            if team_id is not None:
                result[str(team_id)] = {"source_url": source, "kits": kits}
            else:
                print(f"Unmapped kit team: {name}", flush=True)
        if not result:
            print(f"Kits {season}: no supported graphics; existing data preserved", flush=True)
            continue
        catalog["seasons"][str(season)] = result
        missing = [t for t in teams if str(t["team_id"]) not in result]
        catalog.setdefault("coverage", {})[str(season)] = {
            "participant_count": len(teams), "teams_with_kits": len(result),
            "missing_teams": missing,
        }
        if missing:
            print(f"Kits {season}: missing participants: {missing}", flush=True)
        catalog["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        save_data("team_kits.json", catalog)
        print(f"Kits {season}: {len(result)} teams, {sum(len(x['kits']) for x in result.values())} sets", flush=True)
    catalog["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    save_data("team_kits.json", catalog)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values", action="store_true")
    parser.add_argument("--kits", nargs="+", type=int)
    args = parser.parse_args()
    if args.values:
        import_values()
    if args.kits:
        import_kits(args.kits)
