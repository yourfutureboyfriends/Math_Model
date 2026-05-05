"""
Economic Machine Causal Graph

Represents macroeconomic relationships as a directed graph.

Inspired by Bridgewater's "Economic Machine" framework:
- Economic activity is driven by transactions
- Transactions are funded by money + credit
- Credit cycles drive long-term debt patterns
- Productivity growth drives long-term living standards

This module models the transmission of economic shocks through
the system to predict asset impacts.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CausalEdge:
    """
    Represents a causal relationship between two macro nodes.

    Example: policy_rates → valuation_multiples
    """
    from_node: str
    to_node: str
    sign: str  # "positive", "negative"
    channel: str  # mechanism name
    explanation: str
    strength: float = 0.5  # 0-1, based on empirical evidence
    lag_months: int = 1  # typical transmission lag
    confidence: float = 0.7  # research confidence in this relationship


@dataclass
class MacroNode:
    """A node in the economic machine graph."""
    name: str
    category: str  # real, nominal, financial, policy, sentiment
    description: str
    data_series: Optional[str] = None  # FRED series if applicable
    current_value: Optional[float] = None
    direction: str = "stable"  # improving, deteriorating, stable
    zscore: Optional[float] = None


class CausalGraph:
    """
    Economic machine represented as a causal graph.

    Models how shocks propagate through the economy.
    """

    # Standard macro nodes
    DEFAULT_NODES: Dict[str, MacroNode] = {
        # Real activity
        "growth": MacroNode("growth", "real", "Economic growth rate", "GDPC1"),
        "consumption": MacroNode("consumption", "real", "Consumer spending", "PCEC1"),
        "production": MacroNode("production", "real", "Industrial production", "INDPRO"),
        "employment": MacroNode("employment", "real", "Labor market", "PAYEMS"),
        "wages": MacroNode("wages", "real", "Wage growth", "CES0500000003"),
        "business_investment": MacroNode("business_investment", "real", "Capex", "PNFI"),
        "housing": MacroNode("housing", "real", "Housing activity", "HOUST"),

        # Inflation
        "headline_inflation": MacroNode("headline_inflation", "nominal", "CPI all items", "CPIAUCSL"),
        "core_inflation": MacroNode("core_inflation", "nominal", "Core CPI", "CPILFESL"),
        "wage_inflation": MacroNode("wage_inflation", "nominal", "Wage cost pressure", None),
        "inflation_expectations": MacroNode("inflation_expectations", "nominal", "Expected inflation", None),

        # Interest rates
        "policy_rates": MacroNode("policy_rates", "policy", "Central bank policy rate", "FEDFUNDS"),
        "real_rates": MacroNode("real_rates", "financial", "Inflation-adjusted rates", None),
        "yield_curve": MacroNode("yield_curve", "financial", "Term spread", "T10Y2Y"),
        "short_rates": MacroNode("short_rates", "financial", "Short-term rates", "DGS3MO"),
        "long_rates": MacroNode("long_rates", "financial", "Long-term rates", "DGS10"),

        # Credit
        "credit_spreads": MacroNode("credit_spreads", "financial", "Credit risk premium", "BAA10Y"),
        "credit_growth": MacroNode("credit_growth", "financial", "Private credit creation", "BUSLOANS"),
        "financial_conditions": MacroNode("financial_conditions", "financial", "Overall FC index", None),
        "liquidity": MacroNode("liquidity", "financial", "Money market conditions", None),

        # External
        "dollar": MacroNode("dollar", "financial", "USD exchange rate", "DTWEXBGS"),
        "oil": MacroNode("oil", "commodity", "Oil price", "DCOILWTICO"),
        "commodities": MacroNode("commodities", "commodity", "Broad commodities", "PALLFNFINDEXM"),

        # Corporate
        "earnings": MacroNode("earnings", "corporate", "Corporate profits", "CP"),
        "margins": MacroNode("margins", "corporate", "Profit margins", None),
        "valuations": MacroNode("valuations", "market", "P/E multiples", None),

        # Sentiment
        "risk_appetite": MacroNode("risk_appetite", "sentiment", "Risk-on/off sentiment", "VIXCLS"),
        "business_confidence": MacroNode("business_confidence", "sentiment", "Business sentiment", None),
        "consumer_confidence": MacroNode("consumer_confidence", "sentiment", "Consumer sentiment", "UMCSENT"),

        # Asset classes
        "equities": MacroNode("equities", "market", "Stock prices", "SP500"),
        "credit": MacroNode("credit", "market", "Credit returns", None),
        "rates_market": MacroNode("rates_market", "market", "Rates market", None),
    }

    # Key causal relationships
    DEFAULT_EDGES: List[CausalEdge] = [
        # Policy transmission
        CausalEdge("policy_rates", "short_rates", "positive", "policy_transmission",
                   "Policy rate sets short-term market rates", strength=0.9, lag_months=0),
        CausalEdge("short_rates", "real_rates", "positive", "fisher_effect",
                   "Nominal rates less inflation = real rates", strength=0.8, lag_months=1),
        CausalEdge("policy_rates", "yield_curve", "negative", "curve_steer",
                   "Policy affects curve steepness", strength=0.7, lag_months=1),

        # Real economy
        CausalEdge("real_rates", "business_investment", "negative", "cost_of_capital",
                   "Higher real rates raise cost of capital", strength=0.8, lag_months=3),
        CausalEdge("real_rates", "housing", "negative", "mortgage_rates",
                   "Rates affect mortgage affordability", strength=0.8, lag_months=3),
        CausalEdge("credit_spreads", "business_investment", "negative", "credit_supply",
                   "Tighter credit reduces investment", strength=0.7, lag_months=2),
        CausalEdge("employment", "consumption", "positive", "income_effect",
                   "Jobs support spending", strength=0.9, lag_months=1),
        CausalEdge("wages", "consumption", "positive", "wage_income",
                   "Wage growth drives spending", strength=0.8, lag_months=1),

        # Inflation
        CausalEdge("oil", "headline_inflation", "positive", "energy_inflation",
                   "Oil drives energy inflation", strength=0.8, lag_months=1),
        CausalEdge("wages", "wage_inflation", "positive", "wage_cost_pressure",
                   "Tight labor = wage pressure", strength=0.7, lag_months=3),
        CausalEdge("wage_inflation", "core_inflation", "positive", "services_inflation",
                   "Wages drive services costs", strength=0.6, lag_months=6),
        CausalEdge("inflation_expectations", "wage_inflation", "positive", "expectations_embed",
                   "Expectations affect wage demands", strength=0.5, lag_months=6),

        # Financial markets
        CausalEdge("policy_rates", "valuations", "negative", "discount_rate",
                   "Higher rates = higher discount rate", strength=0.8, lag_months=1),
        CausalEdge("earnings", "valuations", "positive", "fundamentals",
                   "Earnings support valuations", strength=0.7, lag_months=0),
        CausalEdge("risk_appetite", "valuations", "positive", "risk_premium",
                   "Risk appetite affects multiples", strength=0.8, lag_months=0),
        CausalEdge("credit_spreads", "valuations", "negative", "credit_channel",
                   "Credit stress hurts multiples", strength=0.7, lag_months=1),
        CausalEdge("dollar", "earnings", "negative", "translation_effect",
                   "Strong dollar hurts multinationals", strength=0.6, lag_months=1),

        # Sentiment feedback
        CausalEdge("employment", "consumer_confidence", "positive", "labor_sentiment",
                   "Jobs drive confidence", strength=0.8, lag_months=1),
        CausalEdge("consumer_confidence", "consumption", "positive", "sentiment_spending",
                   "Confidence affects spending", strength=0.6, lag_months=1),
        CausalEdge("equities", "consumer_confidence", "positive", "wealth_effect",
                   "Wealth drives confidence", strength=0.5, lag_months=1),

        # Credit cycle
        CausalEdge("policy_rates", "credit_growth", "negative", "credit_price",
                   "Rates affect credit demand", strength=0.7, lag_months=3),
        CausalEdge("credit_growth", "business_investment", "positive", "credit_fueled_capex",
                   "Credit enables investment", strength=0.8, lag_months=3),
        CausalEdge("credit_growth", "consumption", "positive", "credit_fueled_spending",
                   "Credit enables consumption", strength=0.7, lag_months=1),

        # Commodities
        CausalEdge("growth", "commodities", "positive", "demand_cycle",
                   "Growth drives commodity demand", strength=0.7, lag_months=1),
        CausalEdge("dollar", "commodities", "negative", "dollar_denominated",
                   "Dollar affects commodity prices", strength=0.7, lag_months=0),
    ]

    def __init__(self):
        self.graph = nx.DiGraph() if HAS_NETWORKX else None
        self.nodes: Dict[str, MacroNode] = {}
        self.edges: Dict[Tuple[str, str], CausalEdge] = {}
        self._adjacency: Dict[str, List[str]] = {}  # Fallback adjacency list

        # Build graph
        self._build_default_graph()

    def _build_default_graph(self) -> None:
        """Initialize with default macro structure."""
        # Add nodes
        for name, node in self.DEFAULT_NODES.items():
            self.add_node(node)

        # Add edges
        for edge in self.DEFAULT_EDGES:
            self.add_edge(edge)

    def add_node(self, node: MacroNode) -> None:
        """Add a macro node."""
        self.nodes[node.name] = node
        self._adjacency[node.name] = []
        if self.graph:
            self.graph.add_node(node.name, **node.__dict__)

    def add_edge(self, edge: CausalEdge) -> None:
        """Add a causal edge."""
        self.edges[(edge.from_node, edge.to_node)] = edge
        self._adjacency.setdefault(edge.from_node, []).append(edge.to_node)
        if self.graph:
            self.graph.add_edge(
                edge.from_node, edge.to_node,
                sign=edge.sign,
                channel=edge.channel,
                strength=edge.strength,
                lag=edge.lag_months,
            )

    def get_downstream_effects(
        self,
        node: str,
        depth: int = 2,
    ) -> List[Tuple[str, float, int]]:
        """
        Find all nodes affected by a shock to given node.

        Returns list of (node_name, cumulative_strength, total_lag).
        """
        if node not in self.nodes:
            return []

        if HAS_NETWORKX and self.graph:
            return self._get_downstream_effects_nx(node, depth)
        return self._get_downstream_effects_fallback(node, depth)

    def _get_downstream_effects_nx(
        self,
        node: str,
        depth: int = 2,
    ) -> List[Tuple[str, float, int]]:
        """NetworkX implementation."""
        effects = []

        # BFS to find all paths
        for target in self.graph.nodes():
            if target == node:
                continue

            paths = list(nx.all_simple_paths(
                self.graph, node, target, cutoff=depth
            ))

            if not paths:
                continue

            # Calculate average effect across all paths
            total_strength = 0
            total_lag = 0

            for path in paths:
                strength = 1.0
                lag = 0

                for i in range(len(path) - 1):
                    edge = self.edges.get((path[i], path[i+1]))
                    if edge:
                        strength *= edge.strength
                        lag += edge.lag_months

                total_strength += strength
                total_lag += lag

            avg_strength = total_strength / len(paths)
            avg_lag = total_lag / len(paths)

            effects.append((target, avg_strength, int(avg_lag)))

        return sorted(effects, key=lambda x: x[1], reverse=True)

    def _get_downstream_effects_fallback(
        self,
        node: str,
        depth: int = 2,
    ) -> List[Tuple[str, float, int]]:
        """Fallback implementation without NetworkX."""
        effects = []
        visited = set()

        def dfs(current: str, path: List[str], strength: float, lag: int):
            if len(path) > depth + 1:
                return

            if len(path) > 1 and current != node:
                effects.append((current, strength, lag))

            for neighbor in self._adjacency.get(current, []):
                if neighbor not in visited:
                    edge = self.edges.get((current, neighbor))
                    if edge:
                        visited.add(neighbor)
                        dfs(neighbor, path + [neighbor],
                            strength * edge.strength,
                            lag + edge.lag_months)
                        visited.remove(neighbor)

        dfs(node, [node], 1.0, 0)

        # Aggregate by target (average if multiple paths)
        agg: Dict[str, List[Tuple[float, int]]] = {}
        for target, strength, lag in effects:
            if target not in agg:
                agg[target] = []
            agg[target].append((strength, lag))

        result = []
        for target, vals in agg.items():
            avg_strength = sum(v[0] for v in vals) / len(vals)
            avg_lag = int(sum(v[1] for v in vals) / len(vals))
            result.append((target, avg_strength, avg_lag))

        return sorted(result, key=lambda x: x[1], reverse=True)

    def get_upstream_causes(
        self,
        node: str,
        depth: int = 2,
    ) -> List[Tuple[str, float]]:
        """Find nodes that typically cause changes in given node."""
        if node not in self.nodes:
            return []

        # Build reverse adjacency
        reverse_adj: Dict[str, List[str]] = {}
        for (from_n, to_n), edge in self.edges.items():
            reverse_adj.setdefault(to_n, []).append(from_n)

        causes = []
        visited = set()

        def dfs(current: str, path: List[str], strength: float):
            if len(path) > depth + 1:
                return

            if len(path) > 1 and current != node:
                causes.append((current, strength))

            for neighbor in reverse_adj.get(current, []):
                if neighbor not in visited:
                    edge = self.edges.get((neighbor, current))
                    if edge:
                        visited.add(neighbor)
                        dfs(neighbor, path + [neighbor], strength * edge.strength)
                        visited.remove(neighbor)

        dfs(node, [node], 1.0)

        # Aggregate
        agg: Dict[str, List[float]] = {}
        for source, strength in causes:
            agg.setdefault(source, []).append(strength)

        result = [(s, sum(v)/len(v)) for s, v in agg.items()]
        return sorted(result, key=lambda x: x[1], reverse=True)

    def _calculate_path_strength(self, path: List[str]) -> float:
        """Calculate cumulative strength along a path."""
        strength = 1.0
        for i in range(len(path) - 1):
            edge = self.edges.get((path[i], path[i+1]))
            if edge:
                strength *= edge.strength
        return strength

    def simulate_shock(
        self,
        node: str,
        shock_magnitude: float = 1.0,
        depth: int = 2,
    ) -> Dict[str, Dict]:
        """
        Simulate effect of a shock to given node.

        Returns dict of affected nodes with predicted magnitude and timing.
        """
        effects = self.get_downstream_effects(node, depth)

        results = {}
        for target, strength, lag in effects:
            # Determine sign
            edge = self.edges.get((node, target))
            sign = 1 if edge and edge.sign == "positive" else -1

            results[target] = {
                "predicted_change": shock_magnitude * strength * sign,
                "confidence": edge.confidence if edge else 0.5,
                "typical_lag_months": lag,
                "transmission_channel": edge.channel if edge else "unknown",
            }

        return results

    def get_active_transmission_channels(
        self,
        changed_nodes: List[str],
    ) -> Dict[str, List[str]]:
        """
        Given a set of changed nodes, identify active transmission channels.
        """
        active = {}

        for node in changed_nodes:
            downstream = self.get_downstream_effects(node, depth=1)
            for target, strength, lag in downstream:
                edge = self.edges.get((node, target))
                if edge:
                    channel = edge.channel
                    if channel not in active:
                        active[channel] = []
                    active[channel].append(f"{node} → {target}")

        return active

    def get_node_state(self, node: str) -> Optional[MacroNode]:
        """Get current state of a node."""
        return self.nodes.get(node)

    def update_node_state(
        self,
        node: str,
        value: float,
        direction: str,
        zscore: Optional[float] = None,
    ) -> None:
        """Update current state of a node."""
        if node in self.nodes:
            self.nodes[node].current_value = value
            self.nodes[node].direction = direction
            self.nodes[node].zscore = zscore

    def get_graph_summary(self) -> Dict:
        """Summary of graph structure."""
        summary = {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "categories": list(set(n.category for n in self.nodes.values())),
        }

        if HAS_NETWORKX and self.graph:
            summary.update({
                "density": nx.density(self.graph),
                "is_weakly_connected": nx.is_weakly_connected(self.graph),
                "longest_path_length": nx.dag_longest_path_length(self.graph)
                if nx.is_directed_acyclic_graph(self.graph) else None,
            })
        else:
            summary.update({
                "density": len(self.edges) / (len(self.nodes) * (len(self.nodes) - 1))
                if len(self.nodes) > 1 else 0,
                "is_weakly_connected": None,
                "longest_path_length": None,
            })

        return summary

    def export_for_visualization(self) -> Dict:
        """Export graph in format suitable for visualization."""
        return {
            "nodes": [
                {
                    "id": name,
                    "category": node.category,
                    "current_value": node.current_value,
                    "direction": node.direction,
                }
                for name, node in self.nodes.items()
            ],
            "links": [
                {
                    "source": edge.from_node,
                    "target": edge.to_node,
                    "sign": edge.sign,
                    "strength": edge.strength,
                    "channel": edge.channel,
                }
                for edge in self.edges.values()
            ],
        }
