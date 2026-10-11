"""Download discharge or river stage from South Africa's DWS database."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests


BASE_URL = "https://www.dws.gov.za/hydrology/Verified/HyData.aspx"
GAUGE_CATALOGUE = Path(__file__).with_name("south_africa_dws_gauges.csv")
DEFAULT_START_DATE = "2023-01-01"
DEFAULT_END_DATE = "2023-12-31"
USER_AGENT = "south-africa-dws-data-downloader/1.0"


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use dates in YYYY-MM-DD format.") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download one DWS river gauge by station number or coordinates."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--gauge", help="DWS gauge number, for example A2H001")
    selector.add_argument(
        "--coordinates",
        nargs=2,
        type=float,
        metavar=("LATITUDE", "LONGITUDE"),
        help="choose the nearest gauge to a latitude and longitude",
    )
    parser.add_argument(
        "--variable",
        choices=("discharge", "stage"),
        default="discharge",
        help="data to download (default: discharge)",
    )
    parser.add_argument(
        "--start-date", type=parse_date, default=parse_date(DEFAULT_START_DATE)
    )
    parser.add_argument(
        "--end-date", type=parse_date, default=parse_date(DEFAULT_END_DATE)
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output CSV path (default: data/<gauge>_<variable>.csv)",
    )
    return parser


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_gauge(latitude: float, longitude: float) -> tuple[str, float, float, float]:
    if not GAUGE_CATALOGUE.exists():
        raise FileNotFoundError(f"Gauge catalogue not found: {GAUGE_CATALOGUE}")

    closest: tuple[str, float, float, float] | None = None
    with GAUGE_CATALOGUE.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            gauge_lat = float(row["latitude"])
            gauge_lon = float(row["longitude"])
            distance = haversine_km(latitude, longitude, gauge_lat, gauge_lon)
            if closest is None or distance < closest[3]:
                closest = (row["site"].strip().upper(), gauge_lat, gauge_lon, distance)

    if closest is None:
        raise RuntimeError("The gauge catalogue is empty.")
    return closest


def date_chunks(start: date, end: date, variable: str):
    """DWS limits primary data to one year and daily data to twenty years."""
    years_per_chunk = 1 if variable == "stage" else 20
    cursor = start
    while cursor <= end:
        try:
            boundary = cursor.replace(year=cursor.year + years_per_chunk) - timedelta(days=1)
        except ValueError:
            boundary = cursor.replace(month=2, day=28, year=cursor.year + years_per_chunk)
        chunk_end = min(boundary, end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def download_page(
    session: requests.Session,
    gauge: str,
    variable: str,
    start: date,
    end: date,
) -> str:
    params = {
        "Station": f"{gauge}100.00",
        "DataType": "Point" if variable == "stage" else "Daily",
        "StartDT": start.isoformat(),
        "EndDT": end.isoformat(),
        "SiteType": "RIV",
    }
    response = session.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.text


def data_lines(html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in html.splitlines():
        stripped = re.sub(r"<[^>]+>", " ", line).strip()
        if re.match(r"^\d{8}\s", stripped):
            rows.append(re.split(r"\s+", stripped))
    return rows


def parse_discharge(html: str, gauge: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for tokens in data_lines(html):
        if len(tokens) < 3:
            continue
        try:
            day = datetime.strptime(tokens[0], "%Y%m%d").date().isoformat()
            float(tokens[1])
        except ValueError:
            continue
        output.append(
            {
                "gauge_id": gauge,
                "date": day,
                "discharge_m3_s": tokens[1],
                "quality_code": tokens[2],
            }
        )
    return output


def parse_stage(html: str, gauge: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for tokens in data_lines(html):
        if len(tokens) < 4:
            continue
        try:
            timestamp = datetime.strptime(tokens[0] + tokens[1].zfill(4), "%Y%m%d%H%M")
            float(tokens[2])
        except ValueError:
            continue
        output.append(
            {
                "gauge_id": gauge,
                "datetime": timestamp.isoformat(sep=" ", timespec="minutes"),
                "stage_m": tokens[2],
                "quality_code": tokens[3],
            }
        )
    return output


def write_csv(path: Path, rows: list[dict[str, str]], variable: str) -> None:
    columns = (
        ["gauge_id", "date", "discharge_m3_s", "quality_code"]
        if variable == "discharge"
        else ["gauge_id", "datetime", "stage_m", "quality_code"]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = build_parser().parse_args()
    if args.start_date > args.end_date:
        print("Error: start date must not be after end date.", file=sys.stderr)
        return 2

    gauge = args.gauge.strip().upper() if args.gauge else ""
    if args.coordinates:
        latitude, longitude = args.coordinates
        gauge, gauge_lat, gauge_lon, distance = nearest_gauge(latitude, longitude)
        print(
            f"Nearest gauge: {gauge} at {gauge_lat:.5f}, {gauge_lon:.5f} "
            f"({distance:.2f} km away)"
        )

    output = args.output or Path("data") / f"{gauge}_{args.variable}.csv"
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.dws.gov.za/hydrology/Verified/hymain.aspx",
        }
    )

    rows: list[dict[str, str]] = []
    chunks = list(date_chunks(args.start_date, args.end_date, args.variable))
    for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        print(f"Downloading {gauge}: {chunk_start} to {chunk_end}")
        try:
            html = download_page(session, gauge, args.variable, chunk_start, chunk_end)
        except requests.RequestException as exc:
            print(f"Download failed: {exc}", file=sys.stderr)
            return 1
        parsed = (
            parse_stage(html, gauge)
            if args.variable == "stage"
            else parse_discharge(html, gauge)
        )
        rows.extend(parsed)
        if index < len(chunks):
            time.sleep(1)

    if not rows:
        print(
            "No records were found. Check the gauge number, date range, and DWS availability.",
            file=sys.stderr,
        )
        return 1

    unique = {
        (row["gauge_id"], row.get("date", row.get("datetime", ""))): row for row in rows
    }
    ordered = [unique[key] for key in sorted(unique)]
    write_csv(output, ordered, args.variable)
    print(f"Saved {len(ordered):,} records to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
