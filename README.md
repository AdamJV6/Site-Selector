# Site Selector — v1 MVP

Deliverable 2 build. Implements the Project Charter's v1 scope: Indiana only,
single tenant profile (fast-casual restaurant), fixed 1-mile trade area,
weighted composite Fit Score with map view.

## What's implemented vs. the charter

| Charter item | Status |
|---|---|
| Address → geocode → trade area | Done (Census Geocoder, free, no key) |
| Census/ACS demand pull | Done (population + median household income, block-group level) |
| Competitor count (1 mi) | Done — **via OpenStreetMap Overpass, not Google Places** (see below) |
| Complementary land use (0.5 mi) | Done — via OpenStreetMap Overpass |
| Manual AADT entry | Done (number input in sidebar, no DOT automation yet) |
| Composite score + sub-score breakdown + tier label | Done |
| Map: site, competitors, complementary uses | Done (Folium) |
| Indiana-only enforcement | Done (rejects non-IN block groups) |

**Deviation from the charter, on purpose:** competitor and complementary-use
lookups use OpenStreetMap's Overpass API instead of Google Places. Overpass
is free and keyless, so this app can go live on Render with zero paid API
setup. Coverage is sparser than Google Places in some areas — swapping in
Google Places (or Placer.ai/SafeGraph/CoStar for the full vision) is a clean
v2 upgrade since `data_pipeline.py` isolates all of this behind
`find_competitors()` / `find_complementary_generators()`.

**Calibration constants are unvalidated.** The normalization constants in
`scoring.py` (e.g., what population count maps to a 100 demand score, how
many competitors zero out the competition score) are first-pass heuristics,
flagged in comments. Validating these against known-good Indiana sites is
exactly the "scoring model" team member's next task per the charter's team
split.

## Project structure

```
geocode.py        # address -> lat/lon + Census block-group FIPS
data_pipeline.py   # ACS demand pull, Overpass competitor/generator search
scoring.py          # weighted Fit Score formula + sub-score normalization
app.py               # Streamlit UI (form, score card, map)
requirements.txt
runtime.txt
render.yaml
.env.example
```

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. A `CENSUS_API_KEY` env var is optional
(raises the Census API rate limit) — copy `.env.example` to `.env` and fill
it in, or `export CENSUS_API_KEY=...` before running, if you want one.

## Deploy to Render

1. Push this folder to a GitHub repo (or a subfolder of your team's repo).
2. In Render: **New +** → **Web Service** → connect the repo.
3. If Render doesn't auto-detect `render.yaml`, set manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
4. (Optional) Add env var `CENSUS_API_KEY` under the service's Environment tab.
5. Deploy. Render gives you a `https://<name>.onrender.com` URL — that's your
   Deliverable 2 link.

## Known limitations (v1, by design per charter)

- Indiana only.
- Single tenant profile (fast-casual restaurant); survey UI only collects the
  minimum needed to demo, not the full business questionnaire from the charter.
- AADT is manually entered, not pulled from Indiana DOT's open data automatically.
- Trade area is a fixed-radius circle, not drive-time or road-network based.
- Free-tier Render web services sleep after inactivity — first load after
  idle can take ~30–60 seconds.
