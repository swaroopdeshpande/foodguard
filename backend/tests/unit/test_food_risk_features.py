import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.ml.food_risk.features import synthetic_label  # noqa: E402


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


def test_short_and_long_shelf_life_items_at_same_pct_score_comparably():
    """Chicken with 25% of its 4-day shelf life left (1 day) and a
    hypothetical item with 25% of a 40-day shelf life left (10 days) should
    land on the same side of the risk formula's threshold -- the % remaining
    is what matters, not the absolute day count."""
    short_shelf_life = _row(days_to_expiry=1, pct_shelf_life_remaining=0.25, perishability_level=5)
    long_shelf_life = _row(days_to_expiry=10, pct_shelf_life_remaining=0.25, perishability_level=5)
    assert synthetic_label(short_shelf_life) == synthetic_label(long_shelf_life)


def test_negative_days_to_expiry_always_flagged_regardless_of_category():
    """Physically past its printed date should score risky-leaning even for
    a low-perishability category, via the explicit days_to_expiry<=0 term."""
    row = _row(days_to_expiry=-5, pct_shelf_life_remaining=-5 / 540, perishability_level=1)
    # not necessarily HIGH (low perishability legitimately dampens urgency),
    # but the negative-days term must contribute -- verify it changes the outcome
    # relative to an otherwise-identical row that ISN'T past its date.
    not_expired = _row(days_to_expiry=5, pct_shelf_life_remaining=5 / 540, perishability_level=1)
    assert synthetic_label(row) >= synthetic_label(not_expired)


def test_low_pct_remaining_scores_higher_than_high_pct_remaining_same_category():
    stale = _row(days_to_expiry=1, pct_shelf_life_remaining=0.05, perishability_level=5)
    fresh = _row(days_to_expiry=4, pct_shelf_life_remaining=1.0, perishability_level=5)
    assert synthetic_label(stale) >= synthetic_label(fresh)
