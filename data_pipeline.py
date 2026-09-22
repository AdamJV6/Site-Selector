"""
data_pipeline.py
Pulls the raw signals the Fit Score needs:
  - Demand data from Census ACS 5-Year estimates (block-group level)
  - Competitor locations from OpenStreetMap (Overpass API)
  - Complementary land-use ("generator") locations from OpenStreetMap

v1 scope: Indiana only, fast-casual restaurant tenant profile,
fixed 1-mile competitor trade area / 0.5-mile complementary-use radius.

No paid API keys required. A free Census API key is optional (raises the
rate limit) — set it as the CENSUS_API_KEY env var if you have one:
https://api.census.gov/data/key_signup.html
"""

import os
import requests

CENSUS_ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Indiana statewide benchmark (2022 ACS 5-year) used to normalize local
# block-group median income. Hardcoded since v1 scope is IN-only; swap
# for a live state-level pull if a later version goes multi-state.
INDIANA_MEDIAN_HOUSEHOLD_INCOME = 64322

# B01003_001E = total population, B19013_001E = median household income
ACS_VARS = "B01003_001E,B19013_001E"

METERS_PER_MILE = 1609.34


def get_acs_demand_data(geo: dict) -> dict:
    """
    Pull population + median household income for the block group
    containing the candidate address. `geo` is geocode.geocode_address()'s
    return value.
    """
    params = {
        "get": ACS_VARS,
        "for": f"block group:{geo['block_group']}",
        "in": f"state:{geo['state_fips']} county:{geo['county_fips']} tract:{geo['tract_fips']}",
    }
    api_key = os.environ.get("CENSUS_API_KEY")
    if api_key:
        params["key"] = api_key

    resp = requests.get(CENSUS_ACS_URL, params=params, timeout=15)
    resp.raise_for_status()
    rows = resp.json()  # [[headers...], [values...]]
    record = dict(zip(rows[0], rows[1]))

    population = int(record.get("B01003_001E") or 0)
    income_raw = record.get("B19013_001E")
    # Census uses -666666666 as a sentinel for suppressed/unavailable data.
    median_income = int(income_raw) if income_raw and int(income_raw) > 0 else None

    return {
        "block_group_population": population,
        "median_household_income": median_income,
    }


def _overpass_search(lat: float, lon: float, radius_m: int, tag_filters: list) -> list:
    """
    Query Overpass for nodes/ways matching any of the given tag filters
    within radius_m meters of (lat, lon). Each filter is either "key=value"
    (exact match) or just "key" (any value).

    Returns a list of dicts: [{"lat": .., "lon": .., "name": ..}, ...]
    Ways are represented by their center point.
    """
    clauses = []
    for f in tag_filters:
        if "=" in f:
            key, value = f.split("=", 1)
            cond = f'["{key}"="{value}"]'
        else:
            cond = f'["{f}"]'
        clauses.append(f'node{cond}(around:{radius_m},{lat},{lon});')
        clauses.append(f'way{cond}(around:{radius_m},{lat},{lon});')

    query = "[out:json][timeout:25];(" + "".join(clauses) + ");out center tags;"
    resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    points = []
    for el in elements:
        if el["type"] == "node":
            p_lat, p_lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center")
            if not center:
                continue
            p_lat, p_lon = center["lat"], center["lon"]
        if p_lat is None or p_lon is None:
            continue
        name = el.get("tags", {}).get("name", "Unnamed")
        points.append({"lat": p_lat, "lon": p_lon, "name": name})
    return points


def find_competitors(lat: float, lon: float, radius_miles: float = 1.0) -> list:
    """
    Direct fast-casual-restaurant-type competitors within radius_miles.
    v1 tenant profile only; broaden/parameterize tags per-vertical in v2.
    """
    radius_m = int(radius_miles * METERS_PER_MILE)
    return _overpass_search(lat, lon, radius_m, ["amenity=fast_food", "amenity=restaurant"])


def find_complementary_generators(lat: float, lon: float, radius_miles: float = 0.5) -> list:
    """
    "Generator" uses within radius_miles that drive complementary foot
    traffic for a fast-casual restaurant: offices, gyms, schools, retail anchors.
    """
    radius_m = int(radius_miles * METERS_PER_MILE)
    tags = [
        "office",
        "leisure=fitness_centre",
        "amenity=gym",
        "amenity=school",
        "amenity=university",
        "amenity=hospital",
        "shop=supermarket",
        "shop=mall",
    ]
    return _overpass_search(lat, lon, radius_m, tags)
