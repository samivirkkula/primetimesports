"""Team identification for followed-team filtering.

Liiga team names come straight from Liiga's API. NHL titles vary by source
("Detroit - St. Louis" on Viaplay, "NHL: Carolina Hurricanes - Winnipeg Jets" on MTV),
so they are matched against a table of the 32 teams and their common names.
"""
from __future__ import annotations

import re

# code, full name, aliases (lowercase, matched as whole words; longest first)
NHL = [
    ("ANA", "Anaheim Ducks", ["anaheim", "ducks"]),
    ("BOS", "Boston Bruins", ["boston", "bruins"]),
    ("BUF", "Buffalo Sabres", ["buffalo", "sabres"]),
    ("CGY", "Calgary Flames", ["calgary", "flames"]),
    ("CAR", "Carolina Hurricanes", ["carolina", "hurricanes"]),
    ("CHI", "Chicago Blackhawks", ["chicago", "blackhawks"]),
    ("COL", "Colorado Avalanche", ["colorado", "avalanche"]),
    ("CBJ", "Columbus Blue Jackets", ["columbus", "blue jackets"]),
    ("DAL", "Dallas Stars", ["dallas", "stars"]),
    ("DET", "Detroit Red Wings", ["detroit", "red wings"]),
    ("EDM", "Edmonton Oilers", ["edmonton", "oilers"]),
    ("FLA", "Florida Panthers", ["florida", "panthers"]),
    ("LAK", "Los Angeles Kings", ["los angeles", "la kings", "kings"]),
    ("MIN", "Minnesota Wild", ["minnesota", "wild"]),
    ("MTL", "Montreal Canadiens", ["montreal", "montréal", "canadiens"]),
    ("NSH", "Nashville Predators", ["nashville", "predators"]),
    ("NJD", "New Jersey Devils", ["new jersey", "devils"]),
    ("NYI", "New York Islanders", ["new york islanders", "ny islanders", "islanders"]),
    ("NYR", "New York Rangers", ["new york rangers", "ny rangers", "rangers"]),
    ("OTT", "Ottawa Senators", ["ottawa", "senators"]),
    ("PHI", "Philadelphia Flyers", ["philadelphia", "flyers"]),
    ("PIT", "Pittsburgh Penguins", ["pittsburgh", "penguins"]),
    ("SJS", "San Jose Sharks", ["san jose", "sharks"]),
    ("SEA", "Seattle Kraken", ["seattle", "kraken"]),
    ("STL", "St. Louis Blues", ["st. louis", "st louis", "saint louis", "blues"]),
    ("TBL", "Tampa Bay Lightning", ["tampa bay", "tampa", "lightning"]),
    ("TOR", "Toronto Maple Leafs", ["toronto", "maple leafs"]),
    ("UTA", "Utah Mammoth", ["utah", "mammoth"]),
    ("VAN", "Vancouver Canucks", ["vancouver", "canucks"]),
    ("VGK", "Vegas Golden Knights", ["vegas", "golden knights"]),
    ("WSH", "Washington Capitals", ["washington", "capitals"]),
    ("WPG", "Winnipeg Jets", ["winnipeg", "jets"]),
]

_SEP = re.compile(r"\s+(?:-|–|—|vs\.?|@)\s+", re.I)
_ALIASES = sorted(((a, code) for code, _, aliases in NHL for a in aliases), key=lambda x: -len(x[0]))


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-zåäöé. ]", " ", text.lower()).replace(".", ". ").replace("  ", " ") + " "


def nhl_team(side: str) -> str | None:
    s = " " + " ".join(_norm(side).split()) + " "
    for alias, code in _ALIASES:
        a = " " + " ".join(_norm(alias).split()) + " "
        if a in s:
            return code
    return None


def nhl_teams(title: str) -> list[str] | None:
    """['DET', 'STL'] for 'Detroit - St. Louis'; None if the title is not a game between two known teams."""
    title = re.sub(r"^\s*NHL\s*[:\-–]?\s*", "", title or "", flags=re.I)
    parts = _SEP.split(title, maxsplit=1)
    if len(parts) != 2:
        return None
    a, b = nhl_team(parts[0]), nhl_team(parts[1])
    return [a, b] if a and b and a != b else None


def nhl_list() -> list[dict]:
    return [{"id": code, "name": name} for code, name, _ in sorted(NHL, key=lambda t: t[1])]
