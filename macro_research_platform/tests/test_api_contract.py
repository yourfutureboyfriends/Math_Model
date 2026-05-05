#!/usr/bin/env python3
"""
API Contract Test — Verifies all dashboard fields are present and non-null.
Run: python3 tests/test_api_contract.py
"""

import requests
import sys
from typing import Any, Dict, List

BASE = "http://localhost:8000"

REQUIRED_PATHS = [
    # Key Metrics (all 6)
    "keyMetrics.growth.value",
    "keyMetrics.inflation.value",
    "keyMetrics.liquidity.value",
    "keyMetrics.risk.value",
    "keyMetrics.recession.value",
    # Regime
    "regime.current",
    "regime.confidence",
    "regime.confidenceScore",
    "regime.duration",
    "regime.history",
    "regime.interpretations",
    # Signals (4 signals with latestScore and history inside)
    "signals.growth.latestScore",
    "signals.inflation.latestScore",
    "signals.liquidity.latestScore",
    "signals.risk.latestScore",
    "signals.growth.history",
    "signals.inflation.history",
    "signals.liquidity.history",
    "signals.risk.history",
    # Sector Allocation
    "sectorAllocation.sectors",
    # Risk Indicators
    "riskIndicators.compositeScore",
    "riskIndicators.indicators",
    # Advanced Indicators
    "advancedIndicators.sahmRule.value",
    "advancedIndicators.creditImpulse.value",
    "advancedIndicators.leiComposite.value",
    # GDP Nowcast
    "nowcast.nowcastQoQ",
    "nowcast.nowcastYoY",
    "nowcast.confidenceInterval.lower",
    "nowcast.confidenceInterval.upper",
    "nowcast.methodology",
    # Liquidity (may be null if data unavailable — that's OK)
    "liquidity.compositeScore",  # Can be null
    "liquidity.regime",  # Can be "DATA_UNAVAILABLE"
    # Sentiment
    "sentiment.compositeRiskAppetite",
    "sentiment.vixTermStructure",
    "sentiment.aaiiSentiment",
    "sentiment.crossAssetMomentum",
    # Valuation
    "valuation.compositeScore",
    # Metadata
    "metadata.latestDate",
    "metadata.dataStatus",
    "metadata.mode",
]


def get_nested(d: Dict, path: str) -> Any:
    """Get nested value from dict by dot-separated path."""
    keys = path.split(".")
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return "__MISSING__"
    return d


def test_dashboard_contract():
    """Test main dashboard endpoint for required fields."""
    print("=" * 60)
    print("API CONTRACT TEST — Dashboard Endpoint")
    print("=" * 60)

    try:
        r = requests.get(f"{BASE}/api/dashboard", timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ FAILED: Cannot connect to {BASE}")
        print("   Is the backend running?")
        sys.exit(1)

    if r.status_code != 200:
        print(f"\n❌ FAILED: Dashboard returned {r.status_code}")
        print(f"   Response: {r.text[:200]}")
        sys.exit(1)

    data = r.json()
    failures = []
    null_fields = []
    warnings = []

    for path in REQUIRED_PATHS:
        val = get_nested(data, path)
        if val == "__MISSING__":
            failures.append(f"MISSING:  {path}")
        elif val is None:
            # Some fields can legitimately be null (e.g., liquidity if no data)
            null_fields.append(f"NULL:     {path}")
        elif val == 0.0 and "score" in path and "composite" not in path:
            warnings.append(f"ZERO:     {path}  ← may be stub")

    # Sector rationale check
    sectors = data.get("sectorAllocation", {}).get("sectors", [])
    stub_rationales = 0
    for s in sectors:
        rat = s.get("rationale", "")
        if "0.00x" in rat or "0.0x" in rat or rat == "":
            stub_rationales += 1
            warnings.append(f"STUB RATIONALE: {s['name']}: '{rat[:50]}...'")

    # Duration check
    duration = data.get("regime", {}).get("duration", 0)
    history = data.get("regime", {}).get("history", [])
    # Only warn if duration equals history length (might be capped) or is suspiciously low
    if duration == 1 and len(history) > 1:
        warnings.append(f"SUSPECT DURATION: {duration} month (likely bug - should be counting consecutive months)")
    elif duration == len(history) and duration < 3:
        warnings.append(f"SUSPECT DURATION: {duration} months (equals history length, may be default)")

    # HY spread unit check
    indicators = data.get("riskIndicators", {}).get("indicators", [])
    for ind in indicators:
        name = ind.get("name", "")
        if "HY" in name or "High Yield" in name or "Credit" in name:
            try:
                val = float(ind.get("value", 0))
                if val < 10 and val > 0:
                    failures.append(f"HY SPREAD UNIT BUG: {val} (should be ~286, not ~2.86)")
                elif val > 100:
                    print(f"   ✓ HY Spread: {val} bps (correct units)")
            except (ValueError, TypeError):
                pass

    # Print results
    print()
    if failures:
        print("❌ CRITICAL FAILURES:")
        for f in failures:
            print(f"   {f}")

    if null_fields:
        print(f"\n⚠️  NULL FIELDS ({len(null_fields)}):")
        for f in null_fields[:10]:  # Limit output
            print(f"   {f}")
        if len(null_fields) > 10:
            print(f"   ... and {len(null_fields) - 10} more")

    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"   {w}")
        if len(warnings) > 10:
            print(f"   ... and {len(warnings) - 10} more")

    if not failures and not null_fields and not warnings:
        print("✅ ALL CHECKS PASSED")
        print(f"   All {len(REQUIRED_PATHS)} required fields present")
        print(f"   {len(sectors)} sectors with valid rationales")
        return 0

    print()
    print("=" * 60)
    print(f"SUMMARY: {len(failures)} failures, {len(null_fields)} nulls, {len(warnings)} warnings")
    print("=" * 60)

    return 1 if failures else 0


def test_sector_rationale():
    """Specifically test sector rationale quality."""
    print("\n" + "=" * 60)
    print("SECTOR RATIONALE TEST")
    print("=" * 60)

    try:
        r = requests.get(f"{BASE}/api/dashboard", timeout=30)
        data = r.json()
    except Exception as e:
        print(f"❌ Failed to fetch: {e}")
        return 1

    sectors = data.get("sectorAllocation", {}).get("sectors", [])
    print(f"\nFound {len(sectors)} sectors:")

    issues = []
    for s in sectors:
        name = s.get("name", "Unknown")
        score = s.get("score", 0)
        rationale = s.get("rationale", "")
        signal = s.get("signal", "")

        print(f"\n  {name}:")
        print(f"    Signal: {signal}")
        print(f"    Score: {score:+.2f}")
        print(f"    Rationale: {rationale[:80]}...")

        # Check for issues
        if "0.00x" in rationale or "0.0x" in rationale:
            issues.append(f"{name}: Contains '0.00x' stub")
        if len(rationale) < 10:
            issues.append(f"{name}: Rationale too short ({len(rationale)} chars)")
        if not rationale:
            issues.append(f"{name}: Empty rationale")

    if issues:
        print("\n❌ RATIONALE ISSUES:")
        for i in issues:
            print(f"   {i}")
        return 1
    else:
        print("\n✅ All rationales look valid")
        return 0


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MACRO RESEARCH PLATFORM — API CONTRACT TEST")
    print("=" * 60)
    print(f"\nTesting against: {BASE}")

    exit_code = test_dashboard_contract()
    exit_code += test_sector_rationale()

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {exit_code} test(s) failed")
    print("=" * 60 + "\n")

    sys.exit(exit_code)
