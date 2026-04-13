"""
Learning system — derives insights from user feedback and injects them
back into the analyzer prompt so future clips get progressively better.
"""

import logging
import statistics
from collections import Counter, defaultdict
from typing import Optional

from database import (
    get_all_feedback_with_clips,
    get_learning_profile,
    save_learning_profile,
)

logger = logging.getLogger(__name__)

# Minimum feedback entries before we start generating pattern insights
MIN_FEEDBACK_FOR_INSIGHTS = 5


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.mean(values), 2)


def _safe_median(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.median(values), 2)


def _accuracy(predicted_score: float, actual_rating: float) -> float:
    """
    Normalised accuracy: 1.0 means perfect match (predicted ≈ actual).
    Both values are in 1–10 range.
    """
    return max(0.0, 1.0 - abs(predicted_score - actual_rating) / 9.0)


# ─── Pattern analysis ─────────────────────────────────────────────────────────

def _analyze_categories(rows: list[dict]) -> dict:
    """Return per-category average performance stats."""
    cat_data: dict[str, list] = defaultdict(list)
    for row in rows:
        cat = row.get("category") or "unknown"
        rating = row.get("performance_rating")
        views = row.get("views") or 0
        if rating:
            cat_data[cat].append({"rating": rating, "views": views})

    result = {}
    for cat, items in cat_data.items():
        ratings = [i["rating"] for i in items]
        views_list = [i["views"] for i in items]
        result[cat] = {
            "count": len(items),
            "avg_rating": _safe_mean(ratings),
            "avg_views": _safe_mean(views_list),
        }
    return result


def _best_performing_categories(cat_stats: dict, top_n: int = 3) -> list[str]:
    """Return the top N category names sorted by avg_rating."""
    sorted_cats = sorted(
        cat_stats.items(),
        key=lambda x: (x[1]["avg_rating"], x[1]["avg_views"]),
        reverse=True,
    )
    return [c[0] for c in sorted_cats[:top_n] if c[1]["count"] >= 2]


def _optimal_duration_range(rows: list[dict]) -> Optional[list[int]]:
    """Find the duration bracket with highest average performance."""
    # Bucket by 10-second intervals
    buckets: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        dur = row.get("duration") or 0
        rating = row.get("performance_rating")
        if dur and rating:
            bucket = (int(dur) // 10) * 10  # floor to nearest 10s
            buckets[bucket].append(rating)

    if not buckets:
        return None

    best_bucket = max(buckets.items(), key=lambda x: _safe_mean(x[1]))
    low = best_bucket[0]
    high = low + 10
    return [low, high]


def _hook_type_analysis(rows: list[dict]) -> list[str]:
    """
    Detect which hook patterns (question, bold statement, story) correlate
    with high performance using simple keyword heuristics.
    """
    patterns = {
        "provocative_question": ["?", "você sabia", "did you know", "o que acontece"],
        "bold_statement": ["nunca", "sempre", "impossível", "never", "always", "impossible", "shocking"],
        "story_opener": ["quando eu", "when i", "once upon", "certa vez", "eu estava"],
        "list_hook": ["3 razões", "5 formas", "top ", "3 reasons", "5 ways"],
    }

    hook_scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        hook = (row.get("hook") or "").lower()
        rating = row.get("performance_rating")
        if not hook or not rating:
            continue
        matched = False
        for pattern_name, keywords in patterns.items():
            if any(kw in hook for kw in keywords):
                hook_scores[pattern_name].append(rating)
                matched = True
        if not matched:
            hook_scores["other"].append(rating)

    if not hook_scores:
        return []

    sorted_hooks = sorted(
        hook_scores.items(),
        key=lambda x: _safe_mean(x[1]),
        reverse=True,
    )
    return [
        h[0] for h in sorted_hooks[:3]
        if _safe_mean(h[1]) >= 6.0 and len(h[1]) >= 2
    ]


def _channel_insights(rows: list[dict]) -> dict:
    """Per-channel average performance."""
    channel_data: dict[str, list] = defaultdict(list)
    for row in rows:
        channel = row.get("channel") or "unknown"
        rating = row.get("performance_rating")
        if rating:
            channel_data[channel].append(rating)

    return {
        ch: {"avg_score": _safe_mean(ratings), "count": len(ratings)}
        for ch, ratings in channel_data.items()
        if len(ratings) >= 2
    }


def _worst_patterns(rows: list[dict]) -> list[str]:
    """Identify categories or patterns that consistently under-perform."""
    patterns = []
    cat_data: dict[str, list] = defaultdict(list)
    for row in rows:
        cat = row.get("category") or "unknown"
        rating = row.get("performance_rating")
        if rating:
            cat_data[cat].append(rating)

    for cat, ratings in cat_data.items():
        if len(ratings) >= 2 and _safe_mean(ratings) < 5.0:
            patterns.append(f"Low-performing category: {cat} (avg {_safe_mean(ratings):.1f}/10)")

    return patterns[:5]


def _generate_learned_rules(
    rows: list[dict],
    cat_stats: dict,
    opt_dur: Optional[list[int]],
) -> list[str]:
    """Generate human-readable rules from the data."""
    rules = []
    n = len(rows)

    # Category rules
    for cat, stats in cat_stats.items():
        if stats["count"] >= 3:
            avg = stats["avg_rating"]
            if avg >= 7.5:
                rules.append(
                    f"'{cat}' clips perform well (avg {avg:.1f}/10 across {stats['count']} clips)"
                )
            elif avg < 5.0:
                rules.append(
                    f"Avoid '{cat}' clips — low performance (avg {avg:.1f}/10)"
                )

    # Duration rules
    if opt_dur:
        rules.append(
            f"Optimal clip duration: {opt_dur[0]}–{opt_dur[1]} seconds"
        )

    # Retention-based rules
    high_retention = [r for r in rows if (r.get("retention_rate") or 0) >= 70]
    if len(high_retention) >= 3:
        dur_vals = [r.get("duration", 0) for r in high_retention if r.get("duration")]
        if dur_vals:
            avg_dur = _safe_mean(dur_vals)
            rules.append(
                f"Clips with >70% retention average {avg_dur:.0f}s — aim for this length"
            )

    # Hook best-moment analysis
    best_moments = Counter(r.get("best_moment") for r in rows if r.get("best_moment"))
    if best_moments:
        top_moment, count = best_moments.most_common(1)[0]
        if count >= 3:
            rules.append(
                f"'{top_moment}' is the most impactful moment in {count}/{n} clips"
            )

    return rules[:8]


# ─── Public API ───────────────────────────────────────────────────────────────

def compute_learning_profile() -> dict:
    """
    Analyse all stored feedback and compute a learning profile.
    Saves the profile to the database and returns it.
    """
    rows = get_all_feedback_with_clips()
    n = len(rows)

    logger.info(f"Computing learning profile from {n} feedback entries …")

    if n < MIN_FEEDBACK_FOR_INSIGHTS:
        profile = {
            "total_clips_rated": n,
            "avg_accuracy": 0.0,
            "best_performing_categories": [],
            "optimal_duration_range": None,
            "best_hook_types": [],
            "worst_patterns": [],
            "channel_insights": {},
            "learned_rules": [
                f"Not enough data yet — rate at least {MIN_FEEDBACK_FOR_INSIGHTS} clips to unlock insights"
            ],
        }
        save_learning_profile(profile)
        return profile

    # Accuracy: compare predicted viral_score to actual performance_rating
    accuracy_vals = []
    for row in rows:
        predicted = row.get("viral_score")
        actual = row.get("performance_rating")
        if predicted is not None and actual is not None:
            accuracy_vals.append(_accuracy(float(predicted), float(actual)))
    avg_accuracy = _safe_mean(accuracy_vals)

    cat_stats = _analyze_categories(rows)
    best_cats = _best_performing_categories(cat_stats)
    opt_dur = _optimal_duration_range(rows)
    best_hooks = _hook_type_analysis(rows)
    worst = _worst_patterns(rows)
    channel_data = _channel_insights(rows)
    rules = _generate_learned_rules(rows, cat_stats, opt_dur)

    profile = {
        "total_clips_rated": n,
        "avg_accuracy": avg_accuracy,
        "best_performing_categories": best_cats,
        "optimal_duration_range": opt_dur,
        "best_hook_types": best_hooks,
        "worst_patterns": worst,
        "channel_insights": channel_data,
        "category_stats": cat_stats,
        "learned_rules": rules,
    }

    save_learning_profile(profile)
    logger.info(
        f"Learning profile updated — accuracy={avg_accuracy:.2%}, "
        f"top categories={best_cats}"
    )
    return profile


def get_profile_for_prompt() -> Optional[dict]:
    """
    Return the current learning profile ready for injection into the analyzer prompt.
    Triggers a recompute if the profile is stale or missing.
    """
    stored = get_learning_profile()
    if stored is None:
        logger.info("No learning profile found — computing fresh …")
        return compute_learning_profile()
    return stored.get("profile_data", stored)


def record_feedback(feedback: dict) -> dict:
    """
    Save a feedback entry to the DB and recompute the learning profile.

    Args:
        feedback: dict with keys: clip_id, performance_rating, views, likes,
                  comments, retention_rate, best_moment, notes.

    Returns:
        Updated learning profile.
    """
    from database import insert_feedback
    insert_feedback(feedback)
    logger.info(f"Feedback recorded for clip {feedback['clip_id']}")
    return compute_learning_profile()
