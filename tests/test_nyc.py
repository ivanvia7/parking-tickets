import json
from pathlib import Path

import pytest

from parking_tickets import cities, groups
from parking_tickets.portals.socrata import dataset_ids
from parking_tickets.schema import hhmmp_time, to_ticket

ROWS = json.loads((Path(__file__).parent / "fixtures" / "nyc.json").read_text())


def test_hhmmp_time():
    assert hhmmp_time("1008P") == "22:08"
    assert hhmmp_time("1208A") == "00:08"
    assert hhmmp_time("1208P") == "12:08"
    assert hhmmp_time("0000") is None
    # Buffalo writes the same clock as '10:08:00PM' from 2022.
    assert hhmmp_time("10:08:00PM") == "22:08"
    assert hhmmp_time("12:45:00AM") == "00:45"
    assert hhmmp_time("1443PM") is None


def test_day_reads_its_fiscal_year_and_the_next():
    city = cities.load("nyc")
    assert dataset_ids(city, "2025-06-03") == ["m5vz-tzqv", "9mwx-gamw"]
    assert dataset_ids(city, "2025-07-01") == ["9mwx-gamw", "pvqr-7yc4"]
    assert dataset_ids(city, "2026-08-01") == ["pvqr-7yc4"]


def test_span_reads_every_fiscal_year_it_crosses():
    city = cities.load("nyc")
    span = dataset_ids(city, "2025-06-01", "2026-08-31")
    assert span == ["m5vz-tzqv", "9mwx-gamw", "pvqr-7yc4"]


def test_fine_comes_from_code_table_by_zone():
    city = cities.load("nyc")
    table = {
        row["violation_code"]: {
            "all_other_areas": "35",
            "manhattan_96th_st_below": "65",
        }
        for row in ROWS
    }
    tickets = [to_ticket(city, row, table) for row in ROWS]
    for row, ticket in zip(ROWS, tickets, strict=True):
        midtown = row.get("violation_precinct") in city["fine_lookup"]["zone_values"]
        assert ticket.fine_usd == (65.0 if midtown else 35.0)
        assert ticket.location and ticket.issued_at.startswith("2025-06-03")


def test_manhattan_zone_pays_the_higher_fine():
    city = cities.load("nyc")
    table = {"14": {"all_other_areas": "95", "manhattan_96th_st_below": "115"}}
    row = {**ROWS[0], "violation_code": "14", "violation_precinct": "14"}
    assert to_ticket(city, row, table).fine_usd == 115.0
    row["violation_precinct"] = "109"
    assert to_ticket(city, row, table).fine_usd == 95.0


def test_day_without_a_listed_dataset_fails():
    with pytest.raises(ValueError, match="2012"):
        dataset_ids(cities.load("nyc"), "2012-01-01")


def test_text_comes_from_code_table_and_blank_amount_is_no_fine():
    city = cities.load("nyc")
    row = {**ROWS[0], "violation_code": "21", "violation_precinct": "109"}
    table = {"21": {"definition": "NO PARKING-STREET CLEANING"}}
    ticket = to_ticket(city, row, table)
    assert ticket.violation_text == "NO PARKING-STREET CLEANING"
    assert ticket.fine_usd is None and ticket.group == "street_cleaning"
    unknown = to_ticket(city, {**row, "violation_code": "0"}, table)
    assert unknown.violation_text is None and unknown.group == "other"


def test_mta_camera_ticket_keeps_its_own_text_and_no_fine():
    # Summons 5700983370 (2024-10-27): code 15 is $115 "NO STANDING-OFF-STREET LOT" in the
    # code table, but the city charged $50 for "MTA CAMERA DOUBLE PARKING".
    city = cities.load("nyc")
    table = {
        "15": {"definition": "NO STANDING-OFF-STREET LOT", "all_other_areas": "115"}
    }
    row = {
        **ROWS[0],
        "violation_code": "15",
        "violation_precinct": "0",
        "issuing_agency": "M",
        "violation_description": "MTA CAMERA DOUBLE PARKING",
    }
    ticket = to_ticket(city, row, table)
    assert ticket.fine_usd is None
    assert ticket.violation_text == "MTA CAMERA DOUBLE PARKING"
    assert ticket.group == "double_parking"


def test_mobile_bus_lane_camera_has_no_fine():
    # Code 12 lists $250; summons 5607338435 paid $50.
    city = cities.load("nyc")
    table = {
        "12": {"definition": "MOBILE BUS LANE VIOLATION", "all_other_areas": "250"}
    }
    row = {
        **ROWS[0],
        "violation_code": "12",
        "issuing_agency": "M",
        "violation_description": "MOBILE BUS LANE VIOLATION",
    }
    ticket = to_ticket(city, row, table)
    assert ticket.fine_usd is None and ticket.group == groups.group_of("nyc", "12")


def test_hand_written_mta_ticket_keeps_the_code_table_fine():
    # Summons 1436914826: agency M, code 14, no description; the city charged $115.
    city = cities.load("nyc")
    table = {
        "14": {"definition": "NO STANDING-DAY/TIME LIMITS", "all_other_areas": "115"}
    }
    row = {
        **ROWS[0],
        "violation_code": "14",
        "violation_precinct": "109",
        "issuing_agency": "M",
    }
    ticket = to_ticket(city, row, table)
    assert ticket.fine_usd == 115.0
    assert ticket.violation_text == "NO STANDING-DAY/TIME LIMITS"


def test_row_description_wins_over_code_table_text():
    city = cities.load("nyc")
    table = {"46": {"definition": "DOUBLE PARKING", "all_other_areas": "115"}}
    row = {
        **ROWS[0],
        "violation_code": "46",
        "violation_description": "46A-Double Parking (Non-COM)",
    }
    ticket = to_ticket(city, row, table)
    assert ticket.violation_text == "46A-Double Parking (Non-COM)"
    assert ticket.fine_usd == 115.0 and ticket.group == groups.group_of("nyc", "46")


def test_bus_lane_camera_has_no_fine():
    # Code 5 lists $250; summonses 4053271277 and 4053270546 paid $50 and $150.
    city = cities.load("nyc")
    table = {"5": {"definition": "BUS LANE VIOLATION", "all_other_areas": "250"}}
    row = {
        **ROWS[0],
        "violation_code": "5",
        "violation_description": "BUS LANE VIOLATION",
    }
    assert to_ticket(city, row, table).fine_usd is None


def test_work_zone_speed_camera_has_no_fine_and_groups_as_speed_camera():
    # Code 90 lists $25; summons 4510000005 paid $50.
    city = cities.load("nyc")
    table = {
        "90": {"definition": "VEH-SALE/WSHNG/RPRNG/DRIVEWAY", "all_other_areas": "25"}
    }
    row = {
        **ROWS[0],
        "violation_code": "90",
        "violation_description": "MTA B&T WORK ZONE SPEED CAM",
    }
    ticket = to_ticket(city, row, table)
    assert ticket.fine_usd is None and ticket.group == "speed_camera"
