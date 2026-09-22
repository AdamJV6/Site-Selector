"""
geocode.py
Geocoding + Census geography lookup using the free Census Bureau Geocoder.
No API key required.
"""

import network_fix  # noqa: F401 — must import before any requests calls; see network_fix.py
import requests

GEOCODER_BASE = "https://geocoding.geo.census.gov/geocoder"
INDIANA_STATE_FIPS = "18"


def geocode_address(address: str) -> dict:
    """
    Geocode a US address using the Census Bureau's free geocoder and
    return coordinates + the Census block-group FIPS codes that contain it,
    in a single call (so ACS lookups downstream don't need a second request).

    Returns:
      {
        "matched_address": str,
        "lat": float,
        "lon": float,
        "state_fips": str,
        "county_fips": str,
        "tract_fips": str,
        "block_group": str,
      }

    Raises ValueError if the address can't be matched or falls outside
    a US Census block group (v1's downstream state check handles
    out-of-Indiana addresses separately).
    """
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "10",  # Census Block Groups
        "format": "json",
    }
    resp = requests.get(f"{GEOCODER_BASE}/geographies/onelineaddress", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise ValueError(
            f"Could not geocode address: {address!r}. Try including city and state."
        )

    match = matches[0]
    coords = match["coordinates"]  # {"x": lon, "y": lat}
    geographies = match.get("geographies", {})
    block_groups = geographies.get("Census Block Groups", [])
    if not block_groups:
        raise ValueError("Address geocoded but no Census Block Group was found for it.")

    bg = block_groups[0]

    return {
        "matched_address": match.get("matchedAddress", address),
        "lat": coords["y"],
        "lon": coords["x"],
        "state_fips": bg["STATE"],
        "county_fips": bg["COUNTY"],
        "tract_fips": bg["TRACT"],
        "block_group": bg["BLKGRP"],
    }


def is_indiana(geo: dict) -> bool:
    """v1 scope check: reject anything outside Indiana."""
    return geo["state_fips"] == INDIANA_STATE_FIPS
