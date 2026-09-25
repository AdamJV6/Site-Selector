# Site Selector — v1 MVP

Deliverable 2 build. Implements the Project Charter's v1 scope: Indiana only,
single tenant profile (fast-casual restaurant), fixed 1-mile trade area,
weighted composite Fit Score with map view.

## What's implemented vs. the charter

| Charter item | Status |
|---|---|
| Address → geocode → trade area | Done (Census Geocoder, free, no key) |
| Census/ACS demand pull | Done (population + median household income, block-group level) — **requires a free Census API key**, see below |
| Competitor count (1 mi) | Done — **via Geoapify Places API, not Google Places or Overpass** (see below) |
| Complementary land use (0.5 mi) | Done — via Geoapify Places API |
| Manual AADT entry | Done (number input, no DOT automation yet) |
| Composite score + sub-score breakdown + tier label | Done |
| Map: site, competitors, complementary uses | Done (Folium) |
| Indiana-only enforcement | Done (rejects non-IN block groups) |
| **Explore a city (beyond charter's v1 scope)** | Done — see below |

### "Explore a city" mode — beyond the charter's original v1 scope

In addition to scoring one address at a time (the charter's exact v1 spec),
the app now has a second tab that samples a grid of candidate points around
a chosen Indiana city's center and ranks them. **Read this before demoing
it:**

- **Candidate points are a sampled grid, not real listings or parcels.**
  v1 has no access to actual available listings (CoStar was explicitly
  deferred in the charter). A high-ranked point means "this general area
  looks promising," not "this specific building is for lease."
- **The ranking is 3-factor, not 4-factor.** Traffic/Access is excluded
  because it's manual-AADT-entry-only in v1 (see charter) and can't
  reasonably be hand-entered for dozens of grid points at once. The three
  remaining factors (Demand 0.30, Competition 0.25, Complementary 0.20)
  are rescaled to sum to 1.0 for this preliminary score — see
  `PRELIM_WEIGHTS` in `scoring.py`. The UI labels this clearly. Once
  you've picked a promising candidate, use the **Score an address** tab
  with a real nearby address and its actual AADT to get the full score.
- **The grid is deliberately small.** Each candidate point costs ~3 API
  calls (1 Census + 2 Geoapify). At the default settings (1.5 mi radius,
  0.5 mi spacing) that's roughly 29 points / ~87 calls per scan — a
  wider radius or tighter spacing scans more thoroughly but takes longer
  and burns through Geoapify's free-tier daily quota faster. Both are
  adjustable sliders in the UI.

**Deviation from the charter, on purpose:** competitor and complementary-use
lookups use the Geoapify Places API instead of Google Places. v1 first tried
OpenStreetMap's free Overpass API to avoid any billing setup, but in
production testing on Render, Overpass's volunteer-run public mirrors
intermittently refused or timed out connections from Render's IP range — a
known anti-abuse pattern these free community servers apply to cloud/
datacenter IPs. Geoapify is a commercial API built for exactly this
server-to-server use case, has a free tier (~3,000 requests/day, no credit
card), and doesn't exhibit that blocking behavior. Swapping in Google Places
later (per the original charter) is still a clean v2 upgrade since
`data_pipeline.py` isolates all of this behind `find_competitors()` /
`find_complementary_generators()`.

**Two free API keys are required to run this for real** (not just
recommended): `CENSUS_API_KEY` and `GEOAPIFY_API_KEY`. Both are free with no
credit card. See "Run locally" / "Deploy to Render" below.

**Calibration constants are unvalidated.** The normalization constants in
`scoring.py` (e.g., what population count maps to a 100 demand score, how
many competitors zero out the competition score) are first-pass heuristics,
flagged in comments. Validating these against known-good Indiana sites is
exactly the "scoring model" team member's next task per the charter's team
split.

## Project structure

```
geocode.py          # address/coords -> lat/lon + Census block-group FIPS
data_pipeline.py     # ACS demand pull, Geoapify competitor/generator search
scoring.py            # weighted Fit Score formula (full + preliminary)
city_scan.py           # Indiana city list, grid generation, city-wide scan
network_fix.py           # works around Render's lack of outbound IPv6
app.py                    # Streamlit UI — "Score an address" + "Explore a city" tabs
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

Opens at http://localhost:8501. Two free API keys are required — copy
`.env.example` to `.env`, fill both in, then `export $(cat .env | xargs)`
before running (or set them however your shell/OS prefers):

- `GEOAPIFY_API_KEY` — sign up free at geoapify.com, no credit card.
- `CENSUS_API_KEY` — sign up free at api.census.gov/data/key_signup.html.

## Deploy to Render

1. Push this folder to a GitHub repo (or a subfolder of your team's repo).
2. In Render: **New +** → **Web Service** → connect the repo.
3. If Render doesn't auto-detect `render.yaml`, set manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
4. Add both env vars under the service's Environment tab: `CENSUS_API_KEY`
   and `GEOAPIFY_API_KEY` (both free, see "Run locally" above for signup links).
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
