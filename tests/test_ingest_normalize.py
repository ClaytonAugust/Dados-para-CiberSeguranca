"""Unit tests for the cross-file normalizers (origin, sectors, regions, software)."""

import csv

import pytest

from cti_graphrag.ingest.models import Malware
from cti_graphrag.ingest.normalize import (
    SoftwareIndex,
    build_report,
    find_countries,
    map_region,
    map_sector,
    parse_origin,
    slugify,
    write_unmapped_sectors,
)
from cti_graphrag.ingest.read import load_dataset


# --- countries -------------------------------------------------------------------
def test_find_countries_names_and_abbreviations():
    assert find_countries("US government and the United Kingdom") == ["US", "GB"]
    assert find_countries("North Korea and South Korea") == ["KP", "KR"]


def test_find_countries_ignores_lowercase_us_and_demonyms():
    assert find_countries("attacks on us and Iranian private sector") == []


# --- origin ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,countries,attribution",
    [
        ("Iran", ("IR",), "attributed"),
        ("China (suspected)", ("CN",), "suspected"),
        ("Not stated in the sources", (), None),
        ("Not attributed to a state", (), None),
        (None, (), None),
        (
            "Based mainly in the United Kingdom and Brazil, per the US Cyber Safety Review Board",
            ("GB", "BR"),
            "attributed",
        ),
    ],
)
def test_parse_origin(raw, countries, attribution):
    origin = parse_origin(raw)
    assert origin.countries == countries
    assert origin.attribution == attribution
    assert origin.raw == raw


# --- sectors -------------------------------------------------------------------------
def test_map_sector_several_sectors_and_a_country():
    mapping = map_sector("Defense, media and communications in Japan")
    assert mapping.sectors == ("defense", "telecommunications", "media")
    assert mapping.countries == ("JP",)


def test_hospitality_is_not_healthcare():
    assert map_sector("Travel and hospitality").sectors == ("hospitality",)


def test_country_in_sector_becomes_country_only():
    mapping = map_sector("Water and wastewater, United States")
    assert mapping.sectors == ()
    assert mapping.countries == ("US",)
    assert mapping.mapped


def test_unmapped_sector():
    assert not map_sector("Critical infrastructure").mapped


def test_it_is_case_sensitive():
    assert map_sector("IT staff").sectors == ("technology",)
    assert map_sector("Website visitors").sectors == ()


# --- regions ----------------------------------------------------------------------------
def test_map_region_list_of_countries():
    assert map_region("Germany, Czechia and France").countries == ("DE", "CZ", "FR")


def test_map_region_keeps_non_countries_raw():
    mapping = map_region("Netherlands and worldwide")
    assert mapping.countries == ("NL",)
    assert mapping.unmapped == ("worldwide",)
    assert map_region("Europe").countries == ()


# --- software ---------------------------------------------------------------------------
@pytest.fixture
def index():
    malware = [
        Malware.model_validate({"name": "Snake", "slug": "snake", "aliases": ["Uroburos"]}),
        Malware.model_validate({"name": "Cobalt Strike", "slug": "cobalt-strike"}),
        Malware.model_validate({"name": "Black Basta", "slug": "black-basta"}),
    ]
    return SoftwareIndex(malware)


@pytest.mark.parametrize(
    "name,url,expected_id,method",
    [
        ("BB", "https://x/knowledge-hub/malware/black-basta/", "software:black-basta", "url_slug"),
        ("cobalt strike", None, "software:cobalt-strike", "name"),
        ("Uroburos", None, "software:snake", "alias"),
        ("Cobalt-Strike!", None, "software:cobalt-strike", "name_slug"),
        ("Mimikatz", None, "software:mimikatz", "new"),
    ],
)
def test_software_match(index, name, url, expected_id, method):
    match = index.match(name, url)
    assert (match.software_id, match.method) == (expected_id, method)


def test_slugify():
    assert slugify("Git (git.exe, gcmd.exe)") == "git-git-exe-gcmd-exe"


# --- real data report ---------------------------------------------------------------------
def test_report_on_real_data():
    report = build_report(load_dataset())
    assert report["tools"] == {
        "refs": 480,
        "by_method": {"name": 90, "new": 351, "alias": 8, "url_slug": 31},
        "malware_reached": 49,
        "new_software_nodes": 333,
    }
    assert report["sectors"]["refs"] == 475
    assert report["origin"] == {"attributed": 39, "no_edge": 11, "suspected": 2}


def test_write_unmapped_sectors(tmp_path):
    path = tmp_path / "unmapped.csv"
    write_unmapped_sectors({"Worldwide": ["a", "b", "a"], "Other": ["c"]}, path)
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["raw_value", "count", "groups"]
    assert rows[1:] == [["Worldwide", "3", "a;b"], ["Other", "1", "c"]]
