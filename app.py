"""
app.py
Streamlit MVP for the Site Selector tool (Deliverable 2).

v1 scope: Indiana only, single tenant profile (fast-casual restaurant),
fixed 1-mile competitor trade area. Two modes:
  - "Score an address": full 4-factor score for one specific address
    (manual AADT entry, per charter v1 scope).
  - "Explore a city": preliminary 3-factor ranking (no Traffic/Access —
    see city_scan.py) across a sampled grid of candidate points around
    a city's center. Points are approximate areas, not real listings.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium

from geocode import geocode_address, is_indiana
from data_pipeline import (
    get_acs_demand_data,
    find_competitors,
    find_complementary_generators,
    INDIANA_MEDIAN_HOUSEHOLD_INCOME,
)
from scoring import compute_fit_score
from city_scan import scan_city, INDIANA_CITIES, DEFAULT_RADIUS_MILES, DEFAULT_SPACING_MILES

st.set_page_config(page_title="Site Selector — v1 (Indiana)", layout="wide")

st.title("Site Selector")
st.caption("MVP — Indiana only · fast-casual restaurant tenant profile")

with st.sidebar:
    st.subheader("About your business (survey — v1 subset)")
    st.selectbox(
        "Business type", ["Fast-casual restaurant"], disabled=True,
        help="v1 supports a single tenant profile; more profiles are a v2 item.",
    )
    st.radio("Do you already have a location open?", ["Yes", "No, this is my first"])

tab_address, tab_city = st.tabs(["Score an address", "Explore a city"])


# ---------------------------------------------------------------- helpers

def run_address_pipeline(address: str, aadt: float):
    with st.spinner("Geocoding address..."):
        try:
            geo = geocode_address(address)
        except ValueError as e:
            st.error(str(e))
            return None
        except Exception as e:
            st.error(f"Geocoding service error: {e}")
            return None

    if not is_indiana(geo):
        st.error(f"'{geo['matched_address']}' is outside Indiana. v1 scope is Indiana-only.")
        return None

    with st.spinner("Pulling Census demand data..."):
        try:
            demand_data = get_acs_demand_data(geo)
            census_warning = None
        except Exception as e:
            census_warning = f"Census data pull failed ({e}); demand sub-score will use population=0."
            demand_data = {"block_group_population": 0, "median_household_income": None}

    with st.spinner("Finding competitors (1 mi)..."):
        try:
            competitors = find_competitors(geo["lat"], geo["lon"])
            competitor_warning = None
        except Exception as e:
            competitor_warning = f"Competitor lookup failed ({e}); assuming none."
            competitors = []

    with st.spinner("Finding complementary land uses (0.5 mi)..."):
        try:
            generators = find_complementary_generators(geo["lat"], geo["lon"])
            generator_warning = None
        except Exception as e:
            generator_warning = f"Complementary land-use lookup failed ({e}); assuming none."
            generators = []

    result = compute_fit_score(
        population=demand_data["block_group_population"],
        median_income=demand_data["median_household_income"],
        state_median_income=INDIANA_MEDIAN_HOUSEHOLD_INCOME,
        competitor_count=len(competitors),
        aadt=aadt,
        generator_count=len(generators),
    )

    return {
        "geo": geo,
        "demand_data": demand_data,
        "competitors": competitors,
        "generators": generators,
        "aadt": aadt,
        "result": result,
        "warnings": [w for w in (census_warning, competitor_warning, generator_warning) if w],
    }


def render_address_results(data: dict):
    geo = data["geo"]
    demand_data = data["demand_data"]
    competitors = data["competitors"]
    generators = data["generators"]
    result = data["result"]

    for w in data["warnings"]:
        st.warning(w)

    st.success(f"Matched: {geo['matched_address']}")

    col1, col2 = st.columns([1, 1.4])

    with col1:
        st.metric("Composite Fit Score", f"{result.composite} / 100", result.tier)
        st.subheader("Sub-scores")
        st.progress(result.demand / 100, text=f"Demand: {result.demand}")
        st.progress(result.competition / 100, text=f"Competition: {result.competition}")
        st.progress(result.traffic / 100, text=f"Traffic/Access: {result.traffic}")
        st.progress(result.complementary / 100, text=f"Complementary Land Use: {result.complementary}")

        with st.expander("Raw inputs"):
            st.write({
                "block_group_population": demand_data["block_group_population"],
                "median_household_income": demand_data["median_household_income"],
                "competitors_within_1mi": len(competitors),
                "generators_within_0.5mi": len(generators),
                "aadt_entered": data["aadt"],
            })

    with col2:
        m = folium.Map(location=[geo["lat"], geo["lon"]], zoom_start=15)
        folium.Marker(
            [geo["lat"], geo["lon"]], tooltip="Candidate site",
            icon=folium.Icon(color="green", icon="star"),
        ).add_to(m)
        folium.Circle(
            [geo["lat"], geo["lon"]], radius=1609.34, color="#1f77b4",
            fill=False, tooltip="1-mile trade area",
        ).add_to(m)
        folium.Circle(
            [geo["lat"], geo["lon"]], radius=804.67, color="#ff7f0e",
            fill=False, tooltip="0.5-mile complementary-use radius",
        ).add_to(m)
        for c in competitors:
            folium.CircleMarker(
                [c["lat"], c["lon"]], radius=5, color="#d62728", fill=True, fill_opacity=0.8,
                tooltip=f"Competitor: {c['name']}",
            ).add_to(m)
        for g in generators:
            folium.CircleMarker(
                [g["lat"], g["lon"]], radius=5, color="#9467bd", fill=True, fill_opacity=0.8,
                tooltip=f"Generator: {g['name']}",
            ).add_to(m)
        st_folium(m, width=None, height=520, key="address_map")


def score_color(score: float) -> str:
    if score >= 65:
        return "#2ca02c"   # green
    if score >= 40:
        return "#ff7f0e"   # orange
    return "#d62728"       # red


def render_city_results(city_name: str, candidates: list):
    if not candidates:
        st.warning("No candidate points returned usable data. Try a different city or widen the grid.")
        return

    st.success(f"Scored {len(candidates)} candidate locations around {city_name}.")
    st.caption(
        "Preliminary ranking — Demand + Competition + Complementary Land Use only "
        "(Traffic/Access requires a manual AADT lookup per site; use the "
        "**Score an address** tab for the full 4-factor score once you've "
        "picked a specific address near a top candidate)."
    )

    center_lat, center_lon = INDIANA_CITIES[city_name]
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    for rank, c in enumerate(candidates, start=1):
        folium.CircleMarker(
            [c["lat"], c["lon"]],
            radius=8,
            color=score_color(c["result"].composite),
            fill=True,
            fill_opacity=0.85,
            tooltip=f"#{rank} — {c['result'].composite}/100 ({c['result'].tier})",
        ).add_to(m)

    col1, col2 = st.columns([1, 1.4])
    with col1:
        st.subheader("Top candidates")
        for rank, c in enumerate(candidates[:10], start=1):
            r = c["result"]
            with st.container(border=True):
                st.markdown(f"**#{rank} — {r.composite}/100 · {r.tier}**")
                st.caption(f"~({c['lat']:.4f}, {c['lon']:.4f})")
                st.progress(r.demand / 100, text=f"Demand: {r.demand}")
                st.progress(r.competition / 100, text=f"Competition: {r.competition}")
                st.progress(r.complementary / 100, text=f"Complementary: {r.complementary}")
    with col2:
        st_folium(m, width=None, height=650, key="city_map")


# ---------------------------------------------------------------- tab 1: address

with tab_address:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        address = st.text_input("Street address", placeholder="123 Main St, Indianapolis, IN", key="address_input")
    with col_b:
        aadt = st.number_input(
            "Nearest DOT count station AADT", min_value=0, step=500, key="aadt_input",
            help=(
                "Look up the closest station on the Indiana DOT open traffic-count map "
                "and enter its Annual Average Daily Traffic figure."
            ),
        )
    run_address = st.button("Score this site", type="primary")

    if run_address:
        if not address:
            st.error("Enter an address to score.")
        else:
            data = run_address_pipeline(address, aadt)
            if data is not None:
                st.session_state["last_address_run"] = data

    if "last_address_run" in st.session_state:
        render_address_results(st.session_state["last_address_run"])
    else:
        st.info("Enter an address above and click **Score this site** to run the model.")


# ---------------------------------------------------------------- tab 2: city

with tab_city:
    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        city_name = st.selectbox("City", list(INDIANA_CITIES.keys()), key="city_select")
    with col_b:
        radius_miles = st.slider("Scan radius (mi)", 0.5, 3.0, DEFAULT_RADIUS_MILES, 0.25, key="city_radius")
    with col_c:
        spacing_miles = st.slider("Grid spacing (mi)", 0.25, 1.0, DEFAULT_SPACING_MILES, 0.25, key="city_spacing")

    approx_points = int(3.14159 * (radius_miles / spacing_miles) ** 2)
    st.caption(
        f"~{approx_points} candidate points, ~{approx_points * 3} API calls. "
        "A wider radius or tighter spacing means a slower scan."
    )

    run_city = st.button("Scan this city", type="primary", key="scan_button")

    if run_city:
        progress_bar = st.progress(0.0, text="Starting scan...")

        def _on_progress(done, total):
            progress_bar.progress(done / total, text=f"Scored {done}/{total} candidate points...")

        candidates = scan_city(city_name, radius_miles, spacing_miles, progress_callback=_on_progress)
        progress_bar.empty()
        st.session_state["last_city_scan"] = {"city_name": city_name, "candidates": candidates}

    if "last_city_scan" in st.session_state:
        scan = st.session_state["last_city_scan"]
        render_city_results(scan["city_name"], scan["candidates"])
    else:
        st.info("Pick a city above and click **Scan this city** to rank candidate locations.")
