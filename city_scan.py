"""
city_scan.py
Powers the "Explore a city" mode: pick an Indiana city, sample a grid of
candidate points around its center, score each on the preliminary
3-factor model (Demand + Competition + Complementary Land Use — no
Traffic/Access, since that's manual-entry-only in v1), and rank them.

IMPORTANT — what this is and isn't:
  - Candidate points are a SAMPLED GRID around the city center, not real
    parcels, vacant storefronts, or listings. v1 has no listings data
    source (CoStar was deferred). A grid point is only ever a rough area
    worth a closer look, not a confirmed available site.
  - Every candidate point costs ~4 API calls (Census ACS + 2x Geoapify
    Places + 1x Geoapify reverse geocode), so the grid is deliberately
    small (see DEFAULT_RADIUS_MILES / DEFAULT_SPACING_MILES below) to keep
    runtime and free-tier API usage reasonable. Widen it if you have
    quota/time to spare.
"""

import math

from geocode import geo_from_coordinates, is_indiana
from data_pipeline import (
    get_acs_demand_data,
    find_competitors,
    find_complementary_generators,
    reverse_geocode,
    INDIANA_MEDIAN_HOUSEHOLD_INCOME,
)
from scoring import compute_preliminary_score

# A handful of Indiana cities with hardcoded center coordinates, so city
# selection doesn't depend on another geocoding call/service. Add more
# freely — just needs an approximate downtown/center lat, lon.
INDIANA_CITIES = {
    "Indianapolis": (39.7684, -86.1581),
    "Fort Wayne": (41.0793, -85.1394),
    "Evansville": (37.9716, -87.5711),
    "South Bend": (41.6764, -86.2520),
    "Carmel": (39.9784, -86.1180),
    "Bloomington": (39.1653, -86.5264),
    "Lafayette": (40.4167, -86.8753),
    "West Lafayette": (40.4259, -86.9081),
    "Fishers": (39.9568, -86.0134),
    "Muncie": (40.1934, -85.3863),
}

MILES_PER_DEGREE_LAT = 69.0

# Kept deliberately small — see module docstring.
DEFAULT_RADIUS_MILES = 1.5
DEFAULT_SPACING_MILES = 0.5


def generate_grid(center_lat: float, center_lon: float,
                   radius_miles: float = DEFAULT_RADIUS_MILES,
                   spacing_miles: float = DEFAULT_SPACING_MILES) -> list:
    """
    Generate approximately evenly-spaced (lat, lon) points inside a circle
    of radius_miles around (center_lat, center_lon). Flat-earth approximation
    (fine at this scale — a couple miles, not hundreds).
    """
    lat_step = spacing_miles / MILES_PER_DEGREE_LAT
    miles_per_degree_lon = MILES_PER_DEGREE_LAT * math.cos(math.radians(center_lat))
    lon_step = spacing_miles / miles_per_degree_lon

    steps = int(radius_miles / spacing_miles) + 1
    points = []
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            dist_miles = math.hypot(i * spacing_miles, j * spacing_miles)
            if dist_miles <= radius_miles:
                points.append((center_lat + i * lat_step, center_lon + j * lon_step))
    return points


def scan_city(city_name: str,
              radius_miles: float = DEFAULT_RADIUS_MILES,
              spacing_miles: float = DEFAULT_SPACING_MILES,
              progress_callback=None) -> list:
    """
    Score every candidate grid point around a city's center. Points that
    fail (outside a block group, API error, etc.) are skipped rather than
    aborting the whole scan.

    progress_callback, if given, is called as progress_callback(done, total)
    after each point — lets the UI show a progress bar.

    Returns a list of dicts sorted by composite score descending:
      {
        "lat": .., "lon": ..,
        "population": .., "median_income": ..,
        "competitor_count": .., "generator_count": ..,
        "result": PreliminaryScoreResult,
      }
    """
    if city_name not in INDIANA_CITIES:
        raise ValueError(f"Unknown city: {city_name!r}")

    center_lat, center_lon = INDIANA_CITIES[city_name]
    grid = generate_grid(center_lat, center_lon, radius_miles, spacing_miles)

    results = []
    for idx, (lat, lon) in enumerate(grid):
        try:
            geo = geo_from_coordinates(lat, lon)
            if not is_indiana(geo):
                continue

            demand_data = get_acs_demand_data(geo)
            competitors = find_competitors(lat, lon)
            generators = find_complementary_generators(lat, lon)
            address = reverse_geocode(lat, lon)

            result = compute_preliminary_score(
                population=demand_data["block_group_population"],
                median_income=demand_data["median_household_income"],
                state_median_income=INDIANA_MEDIAN_HOUSEHOLD_INCOME,
                competitor_count=len(competitors),
                generator_count=len(generators),
            )

            results.append({
                "lat": lat,
                "lon": lon,
                "address": address,
                "population": demand_data["block_group_population"],
                "median_income": demand_data["median_household_income"],
                "competitor_count": len(competitors),
                "generator_count": len(generators),
                "result": result,
            })
        except Exception:
            # Skip points that fail (e.g. a rate-limited call, a point
            # just outside a block group); the scan still returns whatever
            # succeeded rather than failing outright.
            pass
        finally:
            if progress_callback:
                progress_callback(idx + 1, len(grid))

    results.sort(key=lambda r: r["result"].composite, reverse=True)
    return results
