"""
data_pipeline.py
Pulls the raw signals the Fit Score needs:
  - Demand data from Census ACS 5-Year estimates (block-group level)
  - Competitor locations from the Geoapify Places API
  - Complementary land-use ("generator") locations from the Geoapify Places API

v1 scope: Indiana only, fast-casual restaurant tenant profile,
fixed 1-mile competitor trade area / 0.5-mile complementary-use radius.

Requires two free API keys, set as env vars:
  CENSUS_API_KEY   - https://api.census.gov/data/key_signup.html
  GEOAPIFY_API_KEY - https://www.geoapify.com/ (free tier, no credit card)

Note: v1 originally used OpenStreetMap's Overpass API for competitor/
generator lookups (free, keyless). In production testing on Render, the
free community-run Overpass mirrors intermittently refused or timed out
connections from Render's IP range (a known anti-abuse pattern on
volunteer-run infrastructure toward cloud/datacenter IPs). Geoapify is a
commercial API built for exactly this server-to-server use case and
doesn't exhibit that behavior, so v1 uses it instead.
"""

import os
import network_fix  # noqa: F401 — must import before any requests calls; see network_fix.py
import requests

CENSUS_ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"

# Identify the app explicitly; some APIs deprioritize or drop requests
# carrying the default python-requests User-Agent.
HEADERS = {"User-Agent": "SiteSelectorMVP/1.0 (Purdue class project; contact: set-your-email@example.com)"}

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

    resp = requests.get(CENSUS_ACS_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    try:
        rows = resp.json()  # [[headers...], [values...]]
    except ValueError as e:
        # Census sometimes returns an empty/non-JSON body on a malformed
        # query instead of a normal error response. Surface enough detail
        # to debug rather than a bare JSONDecodeError.
        raise ValueError(
            f"Census API returned an unparseable response (status {resp.status_code}, "
            f"body starts with {resp.text[:120]!r}): {e}"
        )
    record = dict(zip(rows[0], rows[1]))

    population = int(record.get("B01003_001E") or 0)
    income_raw = record.get("B19013_001E")
    # Census uses -666666666 as a sentinel for suppressed/unavailable data.
    median_income = int(income_raw) if income_raw and int(income_raw) > 0 else None

    return {
        "block_group_population": population,
        "median_household_income": median_income,
    }


def _geoapify_search(lat: float, lon: float, radius_m: int, categories: list) -> list:
    """
    Query the Geoapify Places API for points matching any of the given
    category keys within radius_m meters of (lat, lon). Category keys are
    Geoapify's hierarchical taxonomy, e.g. "catering.restaurant",
    "commercial.supermarket" — see https://apidocs.geoapify.com/docs/places/

    Returns a list of dicts: [{"lat": .., "lon": .., "name": ..}, ...]
    """
    api_key = os.environ.get("GEOAPIFY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEOAPIFY_API_KEY is not set. Get a free key at geoapify.com and "
            "add it as an environment variable."
        )

    params = {
        "categories": ",".join(categories),
        "filter": f"circle:{lon},{lat},{radius_m}",
        "limit": 100,
        "apiKey": api_key,
    }
    resp = requests.get(GEOAPIFY_PLACES_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    points = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        p_lon, p_lat = coords[0], coords[1]
        name = props.get("name") or props.get("address_line1") or "Unnamed"
        points.append({"lat": p_lat, "lon": p_lon, "name": name})
    return points


def find_competitors(lat: float, lon: float, radius_miles: float = 1.0) -> list:
    """
    Direct fast-casual-restaurant-type competitors within radius_miles.
    v1 tenant profile only; broaden/parameterize categories per-vertical in v2.
    """
    radius_m = int(radius_miles * METERS_PER_MILE)
    return _geoapify_search(lat, lon, radius_m, ["catering.restaurant", "catering.fast_food"])


def find_complementary_generators(lat: float, lon: float, radius_miles: float = 0.5) -> list:
    """
    "Generator" uses within radius_miles that drive complementary foot
    traffic for a fast-casual restaurant: offices, gyms, schools, retail anchors.
    """
    radius_m = int(radius_miles * METERS_PER_MILE)
    categories = [
        "office",
        "commercial.supermarket",
        "commercial.shopping_mall",
        "education.school",
        "education.university",
        "healthcare.hospital",
        "activity.sport_club",
    ]
    return _geoapify_search(lat, lon, radius_m, categories)
