"""
Quick Start Example

Demonstrates basic usage of the Bridgewater-inspired macro research platform.
"""

import sys
sys.path.insert(0, '/Users/daltonyuen/Math_Model/macro_research_platform')

from src.core import create_platform
from src.economic_machine import CausalGraph
from src.data.pit import PointInTimeStore
import pandas as pd
from datetime import datetime


def main():
    print("=" * 60)
    print("Macro Research Platform - Quick Start")
    print("=" * 60)

    # Initialize platform
    print("\n1. Initializing platform...")
    platform = create_platform(environment="development")

    # Check platform status
    status = platform.get_platform_status()
    print(f"   Platform: {status['name']} v{status['version']}")
    print(f"   Environment: {status['environment']}")
    print(f"   Status: {status['status']}")
    print(f"   Components:")
    for component, info in status['components'].items():
        print(f"      - {component}: {info}")

    # Economic regime analysis
    print("\n2. Economic Regime Analysis")
    print("-" * 40)

    # Sample macro data
    macro_data = {
        "growth": 2.5,  # GDP growth %
        "inflation": 3.2,  # CPI %
        "unemployment": 4.1,
        "policy_rate": 5.25,
    }

    regime = platform.get_economic_regime(macro_data)
    print(f"   Current Regime: {regime['regime'].upper()}")
    print(f"   Growth: {regime['growth']}%")
    print(f"   Inflation: {regime['inflation']}%")
    print(f"   Implications:")
    for impl in regime['implications']:
        print(f"      • {impl}")

    # Causal graph analysis
    print("\n3. Causal Graph Analysis")
    print("-" * 40)

    cg = CausalGraph()
    summary = cg.get_graph_summary()
    print(f"   Nodes: {summary['nodes']}")
    print(f"   Edges: {summary['edges']}")
    print(f"   Categories: {summary['categories']}")

    # Simulate a shock
    print(f"\n   Simulating shock: +1% inflation...")
    shock_results = cg.simulate_shock("headline_inflation", shock_magnitude=1.0)
    print(f"   Top 5 affected nodes:")
    for node, info in sorted(shock_results.items(),
                               key=lambda x: abs(x[1]['predicted_change']),
                               reverse=True)[:5]:
        print(f"      • {node}: {info['predicted_change']:+.2f} "
              f"(lag: {info['typical_lag_months']}mo)")

    # Signal registry
    print("\n4. Signal Registry")
    print("-" * 40)

    signals = platform.signal_registry.list_signals()
    print(f"   Registered Signals: {len(signals)}")
    for sig in signals[:3]:
        print(f"      • {sig['name']} ({sig['frequency']})")

    # Research validation
    print("\n5. Research Validation")
    print("-" * 40)

    hypothesis_report = platform.hypothesis_registry.generate_hypothesis_report()
    print(f"   Total Hypotheses: {hypothesis_report['summary']['total_hypotheses']}")
    print(f"   Validated: {hypothesis_report['summary']['by_status'].get('validated', 0)}")
    print(f"   In Production: {hypothesis_report['summary']['by_status'].get('in_production', 0)}")

    print("\n" + "=" * 60)
    print("Quick start complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  • Load historical data with FredMDLoader")
    print("  • Run backtests with WalkForwardValidator")
    print("  • Create custom signals and validate them")
    print("  • Build portfolios with risk budgeting")
    print("  • Run stress tests with scenario analysis")


if __name__ == "__main__":
    main()
