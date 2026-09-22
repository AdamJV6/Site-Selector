"""
app.py
Streamlit MVP for the Site Selector tool (Deliverable 2).

v1 scope: Indiana only, single tenant profile (fast-casual restaurant),
fixed 1-mile competitor trade area, manual AADT entry (DOT automation
deferred to a later version).
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

st.set_page_config(page_title="Site Selector — v1 (Indiana)", layout="wide")

st.title("Site Selector")
st.caption("MVP — Indiana only · fast-casual restaurant tenant profile")

with st.sidebar:
    st.header("Candidate site")
    address = st.text_input("Street address", placeholder="123 Main St, Indianapolis, IN")
    aadt = st.number_input(
        "Nearest DOT count station AADT",
        min_value=0,
        step=500,
        help=(
            "Look up the closest station on the Indiana DOT open traffic-count map "
            "and enter its Annual Average Daily Traffic figure. v1 requires manual "
            "entry; automated parsing of DOT data is deferred to a later version."
        ),
    )
    st.divider()
    st.subheader("About your business (survey — v1 subset)")
    st.selectbox(
        "Business type", ["Fast-casual restaurant"], disabled=True,
        help="v1 supports a single tenant profile; more profiles are a v2 item.",
    )
    st.radio("Do you already have a location open?", ["Yes", "No, this is my first"])
    run = st.button("Score this site", type="primary", use_container_width=True)

if run:
    if not address:
        st.error("Enter an address to score.")
        st.stop()

    with st.spinner("Geocoding address..."):
        try:
            geo = geocode_address(address)
        except ValueError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Geocoding service error: {e}")
            st.stop()

    if not is_indiana(geo):
        st.error(
            f"'{geo['matched_address']}' is outside Indiana. v1 scope is Indiana-only."
        )
        st.stop()

    with st.spinner("Pulling Census demand data..."):
        try:
            demand_data = get_acs_demand_data(geo)
        except Exception as e:
            st.warning(f"Census data pull failed ({e}); demand sub-score will use population=0.")
            demand_data = {"block_group_population": 0, "median_household_income": None}

    with st.spinner("Finding competitors (OpenStreetMap, 1 mi)..."):
        try:
            competitors = find_competitors(geo["lat"], geo["lon"])
        except Exception as e:
            st.warning(f"Competitor lookup failed ({e}); assuming none.")
            competitors = []

    with st.spinner("Finding complementary land uses (OpenStreetMap, 0.5 mi)..."):
        try:
            generators = find_complementary_generators(geo["lat"], geo["lon"])
        except Exception as e:
            st.warning(f"Complementary land-use lookup failed ({e}); assuming none.")
            generators = []

    result = compute_fit_score(
        population=demand_data["block_group_population"],
        median_income=demand_data["median_household_income"],
        state_median_income=INDIANA_MEDIAN_HOUSEHOLD_INCOME,
        competitor_count=len(competitors),
        aadt=aadt,
        generator_count=len(generators),
    )

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
                "aadt_entered": aadt,
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
        st_folium(m, width=None, height=520)
else:
    st.info("Enter an address in the sidebar and click **Score this site** to run the model.")
