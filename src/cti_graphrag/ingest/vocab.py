"""Closed vocabularies used by the normalizer: countries (ISO 3166-1 alpha-2) and sectors.

Only names that occur in the Brandefense data are listed. Demonyms ("Iranian",
"Israeli") are left out on purpose: "Israeli-made equipment" is not a target country.
"""

from __future__ import annotations

import re

# Country names, matched case-insensitively as whole words (longest first).
COUNTRY_NAMES: dict[str, str] = {
    "Afghanistan": "AF",
    "Albania": "AL",
    "Australia": "AU",
    "Azerbaijan": "AZ",
    "Bangladesh": "BD",
    "Brazil": "BR",
    "Canada": "CA",
    "Chile": "CL",
    "China": "CN",
    "Colombia": "CO",
    "Czechia": "CZ",
    "Estonia": "EE",
    "France": "FR",
    "Georgia": "GE",
    "Germany": "DE",
    "Guam": "GU",
    "Hong Kong": "HK",
    "India": "IN",
    "Indonesia": "ID",
    "Iran": "IR",
    "Israel": "IL",
    "Italy": "IT",
    "Japan": "JP",
    "Kazakhstan": "KZ",
    "Kuwait": "KW",
    "Mexico": "MX",
    "Myanmar": "MM",
    "Nepal": "NP",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Nigeria": "NG",
    "North Korea": "KP",
    "Pakistan": "PK",
    "Panama": "PA",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Russia": "RU",
    "Saudi Arabia": "SA",
    "Seychelles": "SC",
    "Singapore": "SG",
    "South Korea": "KR",
    "Taiwan": "TW",
    "Turkey": "TR",
    "Türkiye": "TR",
    "Ukraine": "UA",
    "United Arab Emirates": "AE",
    "United Kingdom": "GB",
    "United States": "US",
    "Vietnam": "VN",
}
# Abbreviations, matched case-sensitively ("US", not the word "us").
COUNTRY_ABBREVIATIONS: dict[str, str] = {"US": "US", "U.S.": "US", "USA": "US", "UK": "GB"}

# Closed sector list (proposal v2) -> keywords, matched case-insensitively.
# "IT" is matched case-sensitively in SECTOR_CASE_SENSITIVE.
SECTOR_KEYWORDS: dict[str, str] = {
    "government": (
        r"government|ministr|public sector|public administration|diplomat|embass|politic"
        r"|election|parliament|state bodies|eu institutions|federal|agenc(?:y|ies)"
        r"|law enforcement|judiciary|courts|intelligence community|emergency services"
        r"|first responders"
    ),
    "defense": r"defen[cs]e|military|naval",
    "aerospace": r"aerospace|aviation",
    "financial": r"financ|bank|insurance|swift|\batms?\b|payment",
    "healthcare": r"health|medical|pharma|\bhospitals?\b|vaccine|biotech|covid|infectious disease",
    "energy": r"energy|nuclear|\boil\b|natural gas|\bpower\b|solar",
    "telecommunications": r"telecom|communication|\bisps?\b|internet providers",
    "technology": (
        r"technolog|\btech\b|software|\bsaas\b|cloud|semiconductor|electronics|digital"
        r"|hosting|service providers|outsourc|\bbpo\b|\bcrm\b|open source|developer"
        r"|kubernetes|certificate authority|cybersecurity"
    ),
    "education": r"educat|universit|academ|school|student",
    "manufacturing": r"manufactur|industrial|metals|steel|chemical|engineering",
    "transportation": r"transport|logistic|shipping|maritime|\bports?\b",
    "retail": r"retail|jewel|commercial facilities",
    "media": r"media|journalist|\bnews\b|entertainment|video games|bloggers",
    "legal": r"legal|law firm",
    "research": r"research|think tank|policy experts|analysts",
    "cryptocurrency": r"crypto|blockchain",
    "ngo": (
        r"\bngos?\b|non-profit|civil society|activist|dissident|labor union|religio"
        r"|international organizations|aid to|opposition"
    ),
    "hospitality": r"hospitality|hotel|lodging|restaurant|casino|gambling|betting|travel|gaming",
    "construction": r"construction|property development",
    "agriculture": r"agricultur|forestry|farm",
}
SECTOR_CASE_SENSITIVE: dict[str, str] = {"technology": r"\bIT\b"}


def _country_pattern() -> re.Pattern[str]:
    names = sorted(COUNTRY_NAMES, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)


def _abbreviation_pattern() -> re.Pattern[str]:
    abbrs = sorted(COUNTRY_ABBREVIATIONS, key=len, reverse=True)
    return re.compile(r"(?<![\w.])(" + "|".join(re.escape(a) for a in abbrs) + r")(?![\w])")


COUNTRY_RE = _country_pattern()
ABBREVIATION_RE = _abbreviation_pattern()
COUNTRY_BY_LOWER = {name.casefold(): iso for name, iso in COUNTRY_NAMES.items()}
SECTOR_RES = {
    slug: [re.compile(pattern, re.IGNORECASE)]
    + ([re.compile(SECTOR_CASE_SENSITIVE[slug])] if slug in SECTOR_CASE_SENSITIVE else [])
    for slug, pattern in SECTOR_KEYWORDS.items()
}
