import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.ml.food_risk.features import deterministic_risk_score, synthetic_label  # noqa: E402


def _row(days_to_expiry, pct_shelf_life_remaining, perishability_level=3, **overrides):
    base = dict(
        days_to_expiry=days_to_expiry, pct_shelf_life_remaining=pct_shelf_life_remaining,
        perishability_level=perishability_level, cumulative_temperature_exposure=0,
        storage_deviation_duration=0, supplier_reliability=0.9, previous_rejection_rate=0,
        consumption_change=0, historical_incidents=0,
    )
    base.update(overrides)
    return pd.Series(base)


def test_fresh_batch_with_large_absolute_days_is_not_flagged_risky():
    """Regression test for the bug found via manual entry: a fresh batch with
    a long absolute shelf life (e.g. rice, 300 of 540 days left) must NOT be
    flagged risky just because the model was ever trained on small absolute
    days_to_expiry values. pct_shelf_life_remaining=0.56 is comfortably fresh."""
    row = _row(days_to_expiry=300, pct_shelf_life_remaining=300 / 540, perishability_level=1)
    assert synthetic_label(row) == 0


def test_short_and_long_shelf_life_items_at_same_pct_score_identically():
    """Chicken with 25% of its 4-day shelf life left (1 day) and a
    hypothetical item with 25% of a 40-day shelf life left (10 days) must
    produce the EXACT SAME deterministic score -- the % remaining is what
    matters, not the absolute day count. Compares the noise-free score
    directly (not the noisy final label) since two independently-drawn
    noise terms can push an equal borderline score to opposite sides of
    the threshold purely by chance -- a real flake found while tuning
    _urgency_cutoff's weight."""
    short_shelf_life = _row(days_to_expiry=1, pct_shelf_life_remaining=0.25, perishability_level=5)
    long_shelf_life = _row(days_to_expiry=10, pct_shelf_life_remaining=0.25, perishability_level=5)
    assert deterministic_risk_score(short_shelf_life) == deterministic_risk_score(long_shelf_life)


def test_near_expiry_highly_perishable_item_is_flagged_risky():
    """The actual real-world case that motivated perishability-scaled
    cutoffs: chicken (perishability 5) with only 1 of 4 days left (25%
    remaining) must score above the label threshold, not be treated as
    safe as fresh just because a flat 25%-for-everyone cutoff put it
    exactly on the boundary."""
    near_expiry_chicken = _row(days_to_expiry=1, pct_shelf_life_remaining=0.25, perishability_level=5)
    assert deterministic_risk_score(near_expiry_chicken) > 0.45


def test_negative_days_to_expiry_always_flagged_regardless_of_category():
    """Physically past its printed date should score risky-leaning even for
    a low-perishability category, via the explicit days_to_expiry<=0 term."""
    row = _row(days_to_expiry=-5, pct_shelf_life_remaining=-5 / 540, perishability_level=1)
    not_expired = _row(days_to_expiry=5, pct_shelf_life_remaining=5 / 540, perishability_level=1)
    assert deterministic_risk_score(row) > deterministic_risk_score(not_expired)


def test_low_pct_remaining_scores_higher_than_high_pct_remaining_same_category():
    stale = _row(days_to_expiry=1, pct_shelf_life_remaining=0.05, perishability_level=5)
    fresh = _row(days_to_expiry=4, pct_shelf_life_remaining=1.0, perishability_level=5)
    assert deterministic_risk_score(stale) > deterministic_risk_score(fresh)


def test_shelf_stable_category_tolerates_lower_pct_before_flagging():
    """Rice (perishability 1) at 10% shelf life remaining should score lower
    urgency than chicken (perishability 5) at the same 10% remaining --
    proving the cutoff is genuinely perishability-scaled, not a flat rule
    that happens to also take perishability_level as an additive term."""
    rice_10pct = _row(days_to_expiry=54, pct_shelf_life_remaining=0.10, perishability_level=1)
    chicken_10pct = _row(days_to_expiry=0.4, pct_shelf_life_remaining=0.10, perishability_level=5)
    assert deterministic_risk_score(rice_10pct) < deterministic_risk_score(chicken_10pct)
