"""
scoring.py
Implements the weighted Fit Score formula from the Project Charter:

    Fit Score = 0.30*Demand + 0.25*Competition + 0.25*Traffic/Access + 0.20*Complementary Land Use

Every sub-score is normalized to a 0-100 scale before weighting.

NOTE ON CALIBRATION: the constants below (DEMAND_POP_BENCHMARK,
COMPETITION_HALF_LIFE, TRAFFIC_AADT_BENCHMARK, GENERATOR_POINTS_PER_SITE)
are first-pass heuristics, not yet validated against known-good sites.
That validation is explicitly scoped in the charter's team split
("scoring model ... validation against known-good sites") — treat these
as v1 defaults to be tuned, not final answers.
"""

from dataclasses import dataclass, asdict

WEIGHTS = {
    "demand": 0.30,
    "competition": 0.25,
    "traffic": 0.25,
    "complementary": 0.20,
}

# --- Calibration constants (flag for validation, see module docstring) ---
DEMAND_POP_BENCHMARK = 12000        # population in trade area for a full 100 pop-score
DEMAND_POP_WEIGHT = 0.6
DEMAND_INCOME_WEIGHT = 0.4
COMPETITION_HALF_LIFE = 6           # competitors it takes for the competition score to halve (exponential decay, see below)
TRAFFIC_AADT_BENCHMARK = 30000      # AADT for a full 100 traffic score
GENERATOR_POINTS_PER_SITE = 10      # points gained per generator within 0.5mi

TIER_LABELS = [
    (80, "Excellent Fit"),
    (65, "Strong Fit"),
    (50, "Moderate Fit"),
    (35, "Weak Fit"),
    (0, "Poor Fit"),
]


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def demand_subscore(population: int, median_income, state_median_income: float) -> float:
    pop_score = _clamp((population / DEMAND_POP_BENCHMARK) * 100)
    if median_income is None:
        # Income suppressed at block-group level; fall back to population only.
        return round(pop_score, 1)
    income_score = _clamp((median_income / state_median_income) * 100)
    return round(DEMAND_POP_WEIGHT * pop_score + DEMAND_INCOME_WEIGHT * income_score, 1)


def competition_subscore(competitor_count: int) -> float:
    """
    Exponential decay rather than a linear penalty: the score halves every
    COMPETITION_HALF_LIFE competitors, so it keeps differentiating between
    "very saturated" and "extremely saturated" markets instead of clipping
    to a hard 0 past some fixed competitor count. It gets arbitrarily close
    to 0 for large competitor counts but (mathematically) never exactly
    hits it — which is the intended behavior, since a real market can
    always be a little more or less saturated than another.
    """
    score = 100 * (0.5 ** (competitor_count / COMPETITION_HALF_LIFE))
    return round(_clamp(score), 1)


def traffic_subscore(aadt: float) -> float:
    return round(_clamp((aadt / TRAFFIC_AADT_BENCHMARK) * 100), 1)


def complementary_subscore(generator_count: int) -> float:
    return round(_clamp(generator_count * GENERATOR_POINTS_PER_SITE), 1)


def tier_label(composite: float) -> str:
    for threshold, label in TIER_LABELS:
        if composite >= threshold:
            return label
    return "Poor Fit"


@dataclass
class FitScoreResult:
    demand: float
    competition: float
    traffic: float
    complementary: float
    composite: float
    tier: str

    def to_dict(self):
        return asdict(self)


def compute_fit_score(
    population: int,
    median_income,
    state_median_income: float,
    competitor_count: int,
    aadt: float,
    generator_count: int,
) -> FitScoreResult:
    demand = demand_subscore(population, median_income, state_median_income)
    competition = competition_subscore(competitor_count)
    traffic = traffic_subscore(aadt)
    complementary = complementary_subscore(generator_count)

    composite = round(
        WEIGHTS["demand"] * demand
        + WEIGHTS["competition"] * competition
        + WEIGHTS["traffic"] * traffic
        + WEIGHTS["complementary"] * complementary,
        1,
    )

    return FitScoreResult(
        demand=demand,
        competition=competition,
        traffic=traffic,
        complementary=complementary,
        composite=composite,
        tier=tier_label(composite),
    )


def explain_fit_score(
    population: int,
    median_income,
    state_median_income: float,
    competitor_count: int,
    aadt: float,
    generator_count: int,
    tenant_profile: str,
    result: FitScoreResult,
) -> str:
    """
    Render a plain-English, numbers-included walkthrough of how each
    sub-score and the composite were actually calculated for one scored
    site — meant to be read by a person (grader, teammate, the business
    owner) alongside the score card, not just the bare numbers. Lives
    next to the formula itself on purpose, so the explanation can't drift
    out of sync with the math it's describing.
    """
    lines = []

    # --- Demand ---
    pop_pct = round((population / DEMAND_POP_BENCHMARK) * 100)
    demand_text = (
        f"**Demand — {result.demand}/100 (30% of composite).** "
        f"This block group has an estimated population of {population:,} "
        f"(U.S. Census ACS 5-year estimate) against a benchmark of "
        f"{DEMAND_POP_BENCHMARK:,} for a full population score — "
        f"{pop_pct}% of that benchmark."
    )
    if median_income is not None:
        income_pct = round((median_income / state_median_income) * 100)
        demand_text += (
            f" Median household income here is ${median_income:,}, which is "
            f"{income_pct}% of the Indiana state median (${state_median_income:,.0f}). "
            f"Demand blends these {int(DEMAND_POP_WEIGHT * 100)}% population / "
            f"{int(DEMAND_INCOME_WEIGHT * 100)}% income."
        )
    else:
        demand_text += (
            " Income data was suppressed at the block-group level (common in low-population "
            "areas, per Census privacy rules), so this score uses population only."
        )
    lines.append(demand_text)

    # --- Competition ---
    lines.append(
        f"**Competition — {result.competition}/100 (25% of composite).** "
        f"{competitor_count} direct {tenant_profile.lower()} competitor"
        f"{'' if competitor_count == 1 else 's'} found within 1 mile. The score decays "
        f"exponentially — halving every {COMPETITION_HALF_LIFE} competitors — rather than "
        f"hitting a hard floor, so it keeps distinguishing \"somewhat saturated\" from "
        f"\"extremely saturated\" markets instead of calling them both a flat 0."
    )

    # --- Traffic ---
    aadt_pct = round((aadt / TRAFFIC_AADT_BENCHMARK) * 100) if aadt else 0
    lines.append(
        f"**Traffic/Access — {result.traffic}/100 (25% of composite).** "
        f"Based on the manually entered AADT (Annual Average Daily Traffic) of "
        f"{int(aadt):,} vehicles/day for the nearest DOT count station, against a "
        f"benchmark of {TRAFFIC_AADT_BENCHMARK:,} AADT for a full score — "
        f"{aadt_pct}% of that benchmark."
    )

    # --- Complementary ---
    lines.append(
        f"**Complementary Land Use — {result.complementary}/100 (20% of composite).** "
        f"{generator_count} nearby generator{'' if generator_count == 1 else 's'} "
        f"(offices, schools, universities, hospitals, supermarkets, malls, or fitness "
        f"centers) found within 0.5 miles, worth {GENERATOR_POINTS_PER_SITE} points each."
    )

    # --- Composite ---
    lines.append(
        f"**Composite:** (0.30 × {result.demand}) + (0.25 × {result.competition}) + "
        f"(0.25 × {result.traffic}) + (0.20 × {result.complementary}) = "
        f"**{result.composite}/100 — {result.tier}.**"
    )

    return "\n\n".join(lines)


# --- Preliminary (3-factor) scoring for the city-wide scan ---
# The city scan generates many candidate points automatically and can't
# ask a human to look up AADT for each one (Traffic/Access is manual-entry
# only in v1 — see charter). So the scan ranks on Demand + Competition +
# Complementary Land Use only, with their charter weights (0.30/0.25/0.20)
# rescaled to sum to 1.0. This is explicitly a preliminary ranking, not a
# substitute for the full 4-factor score — the UI must label it as such.
_PRELIM_WEIGHT_SUM = WEIGHTS["demand"] + WEIGHTS["competition"] + WEIGHTS["complementary"]
PRELIM_WEIGHTS = {
    "demand": WEIGHTS["demand"] / _PRELIM_WEIGHT_SUM,
    "competition": WEIGHTS["competition"] / _PRELIM_WEIGHT_SUM,
    "complementary": WEIGHTS["complementary"] / _PRELIM_WEIGHT_SUM,
}


@dataclass
class PreliminaryScoreResult:
    demand: float
    competition: float
    complementary: float
    composite: float
    tier: str

    def to_dict(self):
        return asdict(self)


def compute_preliminary_score(
    population: int,
    median_income,
    state_median_income: float,
    competitor_count: int,
    generator_count: int,
) -> PreliminaryScoreResult:
    demand = demand_subscore(population, median_income, state_median_income)
    competition = competition_subscore(competitor_count)
    complementary = complementary_subscore(generator_count)

    composite = round(
        PRELIM_WEIGHTS["demand"] * demand
        + PRELIM_WEIGHTS["competition"] * competition
        + PRELIM_WEIGHTS["complementary"] * complementary,
        1,
    )

    return PreliminaryScoreResult(
        demand=demand,
        competition=competition,
        complementary=complementary,
        composite=composite,
        tier=tier_label(composite),
    )
