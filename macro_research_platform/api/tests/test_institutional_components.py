"""The four institutional components that were written but never wired in.

state_store, fusion, incremental_graph and foraging_agent had zero importers — not even a test —
so nothing had ever executed them. They are the System 1 / System 2 boundary (bitemporal feature
store), the heterogeneous fusion into the TFT encoder, the sliding-window VAR-Lasso graph updater,
and the behaviour-cloned foraging agent. These tests pin the contracts that matter before anything
depends on them: no future leakage, dimensional compatibility, causal edge direction, and the
behaviour-cloning-before-online gate.

Runs in the torch group; see TORCH_TESTS in the Makefile.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import torch

from api.tests.test_advanced_autonomous import batch, system

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── Component 1: asynchronous feature store, bitemporal PIT ──────────────────────────────────
@pytest.fixture
def store(tmp_path):
    from api.ml.institutional.state_store import StatefulFeatureStore, TensorSlot

    receipt = [T0 + timedelta(days=10)]        # System 2 computation lands 10 days late
    s = StatefulFeatureStore(
        tmp_path / "state.db",
        {"adjacency": TensorSlot((5, 5)), "debate": TensorSlot((4,))},
        schema_id="test-v1",
        atomic_groups=(("adjacency", "debate"),),
        clock=lambda: receipt[0],
    )
    return s, receipt


def _publish(store, tensors, effective_at):
    return asyncio.run(store.publish(tensors, effective_at=effective_at))


def _both():
    return {"adjacency": torch.eye(5), "debate": torch.ones(4)}


def test_a_late_write_does_not_become_available_at_its_source_date(store):
    """The whole point of storing receipt time separately from effective time."""
    s, _ = store
    _publish(s, _both(), effective_at=T0)
    # Queried as of one day after the source date, the write had not been received yet.
    assert s.get_tensor_snapshot(T0 + timedelta(days=1)) == {}
    # By the receipt date it is visible.
    snap = s.get_tensor_snapshot(T0 + timedelta(days=10))
    assert set(snap) == {"adjacency", "debate"} and snap["adjacency"].shape == (5, 5)


def test_snapshot_tensors_are_private_cpu_copies(store):
    s, _ = store
    _publish(s, _both(), effective_at=T0)
    snap = s.get_tensor_snapshot(T0 + timedelta(days=10))
    snap["adjacency"].zero_()
    assert s.get_tensor_snapshot(T0 + timedelta(days=10))["adjacency"].diagonal().sum() == 5


def test_future_effective_and_partial_atomic_groups_are_refused(store):
    s, _ = store
    with pytest.raises(ValueError, match="Future-effective"):
        _publish(s, _both(), effective_at=T0 + timedelta(days=999))
    with pytest.raises(ValueError, match="atomic"):
        _publish(s, {"adjacency": torch.eye(5)}, effective_at=T0)


def test_unregistered_keys_and_bad_shapes_are_refused(store):
    s, _ = store
    with pytest.raises(ValueError, match="Unregistered"):
        _publish(s, {"adjacency": torch.eye(5), "debate": torch.ones(4), "surprise": torch.ones(2)},
                 effective_at=T0)
    with pytest.raises(ValueError, match="shape"):
        _publish(s, {"adjacency": torch.eye(6), "debate": torch.ones(4)}, effective_at=T0)
    with pytest.raises(ValueError, match="Nonfinite"):
        _publish(s, {"adjacency": torch.full((5, 5), float("nan")), "debate": torch.ones(4)},
                 effective_at=T0)


def test_a_reused_schema_id_with_different_slots_is_refused(tmp_path):
    from api.ml.institutional.state_store import StatefulFeatureStore, TensorSlot

    StatefulFeatureStore(tmp_path / "s.db", {"a": TensorSlot((2,))}, schema_id="dup")
    with pytest.raises(ValueError, match="incompatible"):
        StatefulFeatureStore(tmp_path / "s.db", {"a": TensorSlot((3,))}, schema_id="dup")


# ── Component 2: graph cross-attention and FiLM into the TFT encoder ─────────────────────────
def test_cross_attention_maps_51_graph_nodes_onto_tft_time_steps():
    from api.ml.institutional.fusion import GraphCrossAttentionLayer

    B, T, Ht, N, Hg = 3, 12, 32, 51, 16
    layer = GraphCrossAttentionLayer(temporal_dim=Ht, graph_dim=Hg, heads=4)
    out = layer(torch.randn(B, T, Ht), torch.randn(B, N, Hg))
    assert out.shape == (B, T, Ht)                       # [B,T,Ht] x [B,N,Hg] -> [B,T,Ht]
    assert torch.isfinite(out).all()


def test_cross_attention_masks_padded_nodes_and_rejects_fully_padded_rows():
    from api.ml.institutional.fusion import GraphCrossAttentionLayer

    B, T, Ht, N, Hg = 2, 6, 16, 51, 8
    layer = GraphCrossAttentionLayer(temporal_dim=Ht, graph_dim=Hg, heads=2)
    mask = torch.ones(B, N, dtype=torch.bool)
    mask[0, 40:] = False
    assert layer(torch.randn(B, T, Ht), torch.randn(B, N, Hg), mask).shape == (B, T, Ht)
    mask[1, :] = False                                   # a sample with no real node
    with pytest.raises(ValueError, match="unpadded"):
        layer(torch.randn(B, T, Ht), torch.randn(B, N, Hg), mask)


def test_cross_attention_rejects_dimension_mismatches():
    from api.ml.institutional.fusion import GraphCrossAttentionLayer

    layer = GraphCrossAttentionLayer(temporal_dim=32, graph_dim=16, heads=4)
    with pytest.raises(ValueError, match="Expected temporal"):
        layer(torch.randn(3, 12, 31), torch.randn(3, 51, 16))     # wrong TFT hidden width
    with pytest.raises(ValueError, match="Expected temporal"):
        layer(torch.randn(3, 12, 32), torch.randn(4, 51, 16))     # batch mismatch
    with pytest.raises(ValueError, match="Invalid cross-attention dimensions"):
        GraphCrossAttentionLayer(temporal_dim=32, graph_dim=16, heads=3, attention_dim=8)  # 8 % 3


def test_film_is_identity_at_initialisation_then_learns_to_modulate():
    from api.ml.institutional.fusion import FiLMModulator

    B, T, H, C = 2, 7, 16, 4
    film = FiLMModulator(hidden_dim=H, condition_dim=C)
    h = torch.randn(B, T, H)
    # Zero-initialised output layer => gamma 1, beta 0 => a pretrained encoder is undisturbed.
    assert torch.allclose(film(h, torch.randn(B, C)), h, atol=1e-6)
    with torch.no_grad():                                  # perturb it, as training would
        film.mlp[-1].weight.normal_(0, 0.5)
        film.mlp[-1].bias.normal_(0, 0.1)
    out = film(h, torch.randn(B, C))
    assert out.shape == (B, T, H) and not torch.allclose(out, h)


def test_film_rejects_a_mismatched_condition_vector():
    from api.ml.institutional.fusion import FiLMModulator

    film = FiLMModulator(hidden_dim=16, condition_dim=4)
    with pytest.raises(ValueError, match="FiLM expects"):
        film(torch.randn(2, 7, 16), torch.randn(2, 3))     # debate produced 3 scalars, not 4


# ── Component 4: sliding-window VAR-Lasso with EMA blending ──────────────────────────────────
@pytest.fixture
def updater():
    from api.ml.institutional.incremental_graph import IncrementalCausalUpdater

    nodes = tuple(f"feature:x{i}" for i in range(4))
    return IncrementalCausalUpdater(nodes, lags=2, window=252, ema_alpha=0.3), nodes


def _var_frame(nodes, periods=300, seed=0):
    idx = pd.date_range("2015-01-31", periods=periods, freq="ME", tz="UTC")
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(periods, len(nodes))), index=idx, columns=nodes)
    # plant a real lag-1 edge x0 -> x1 so the Lasso has something to find
    df[nodes[1]] = df[nodes[0]].shift(1).fillna(0) * 0.9 + rng.normal(scale=0.05, size=periods)
    return df


def test_var_lasso_recovers_a_planted_edge_and_emits_a_lagged_dag(updater):
    u, nodes = updater
    df = _var_frame(nodes)
    structure = u.update(df, cutoff=df.index[-1].to_pydatetime())
    assert structure.edges, "a planted lag-1 edge was not recovered"
    assert all(lag >= 1 for _, _, lag in structure.edges), "an edge must carry a positive lag"
    assert (u.adjacency > 0).sum() == len(structure.edges)


def test_graph_tensors_are_time_expanded_and_strictly_forward_in_time(updater):
    u, nodes = updater
    df = _var_frame(nodes)
    u.update(df, cutoff=df.index[-1].to_pydatetime())
    n, L = len(nodes), u.lags
    gt = u.graph_tensors(torch.tensor(df.iloc[-(L + 1):].to_numpy(), dtype=torch.float32))
    assert gt["graph_nodes"].shape == (1, (L + 1) * n, 20)      # [1,(L+1)N,20]
    assert gt["causal_mask"].shape == ((L + 1) * n,) * 2        # [destination, source]
    src, dst = gt["edge_index"]
    assert src.numel() == dst.numel() == gt["edge_weight"].numel()
    assert bool(((src // n) < (dst // n)).all()), "an edge points backwards in time"
    dst_t, src_t = dst // n, src // n
    assert bool(((dst_t - src_t) >= 1).all()) and bool(((dst_t - src_t) <= L).all())


def test_ema_blends_rather_than_replacing_the_previous_graph(updater):
    u, nodes = updater
    first = _var_frame(nodes, seed=0)
    u.update(first, cutoff=first.index[-1].to_pydatetime())
    before = u.adjacency.copy()
    second = _var_frame(nodes, seed=7)                          # a different draw
    u.update(second, cutoff=second.index[-1].to_pydatetime())
    assert not np.allclose(u.adjacency, before), "the EMA did not move the adjacency"
    # alpha=0.3, so at least 70% of the previous mass survives on edges that persist
    both = (before > 0) & (u.adjacency > 0)
    assert both.any() and np.all(u.adjacency[both] >= 0.7 * before[both] - 1e-9)


def test_backdated_and_misaligned_updates_are_refused(updater):
    u, nodes = updater
    df = _var_frame(nodes)
    u.update(df, cutoff=df.index[-1].to_pydatetime())
    with pytest.raises(ValueError, match="Backdated"):
        u.update(df, cutoff=(df.index[-1] - pd.Timedelta(days=400)).to_pydatetime())
    with pytest.raises(ValueError, match="schema mismatch"):
        u.update(df[list(reversed(df.columns))], cutoff=df.index[-1].to_pydatetime())
    naive = df.copy()
    naive.index = df.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone"):
        u.update(naive, cutoff=df.index[-1].to_pydatetime())


def test_only_observed_feature_nodes_are_accepted():
    from api.ml.institutional.incremental_graph import IncrementalCausalUpdater

    with pytest.raises(ValueError, match="feature node"):
        IncrementalCausalUpdater(("provenance:x", "feature:y"))
    with pytest.raises(ValueError, match="Unique"):
        IncrementalCausalUpdater(("feature:x", "feature:x"))


# ── Component 5: behaviour-cloned foraging agent ─────────────────────────────────────────────
def test_composite_reward_reports_no_accuracy_until_labels_mature():
    from api.ml.institutional.foraging_agent import RewardWeights, composite_foraging_reward

    before, after = np.full(24, 0.5), np.full(24, 0.8)
    r = composite_foraging_reward(before, after, cost=0.01, weights=RewardWeights())
    assert r["accuracy_brier_gain"] == 0.0, "accuracy must not be invented without matured labels"
    assert r["information_kl"] > 0
    assert r["reward"] == pytest.approx(
        RewardWeights().information * r["information_kl"] - RewardWeights().cost * 0.01)
    labelled = composite_foraging_reward(before, after, cost=0.01, targets=np.ones(24),
                                         known=np.ones(24, dtype=bool))
    assert labelled["accuracy_brier_gain"] > 0 and labelled["reward"] > r["reward"]


def test_composite_reward_fails_closed_on_invalid_distributions():
    from api.ml.institutional.foraging_agent import composite_foraging_reward

    with pytest.raises(ValueError, match="Invalid TFT reward distributions"):
        composite_foraging_reward(np.full(24, 1.5), np.full(24, 0.5), cost=0.0)
    with pytest.raises(ValueError, match="Invalid TFT reward distributions"):
        composite_foraging_reward(np.full(12, 0.5), np.full(12, 0.5), cost=0.0)   # wrong horizon
    with pytest.raises(ValueError, match="Invalid reward weights"):
        composite_foraging_reward(np.full(24, 0.5), np.full(24, 0.5), cost=float("nan"))


@pytest.fixture
def offline_env():
    from api.ml.institutional.foraging import ModelQueryEpisode, model_foraging_environment

    m, b = system().eval(), batch()
    episode = ModelQueryEpisode('2026-01-01T12:00:00Z', 'fixed', {'Fed': '2026-01-01T11:00:00Z'},
                                b, {'Fed': b}, {'Fed': 'snapshot'}, np.zeros((4, 6)),
                                '2026-02-01T00:00:00Z')
    return model_foraging_environment(m, [episode], cutoff='2026-03-01T00:00:00Z', model_digest='fixed')


def test_agent_refuses_a_live_environment_and_training_before_cloning(offline_env):
    from api.ml.institutional.foraging_agent import ForagingAgent

    agent = ForagingAgent(offline_env, rollout_steps=16, maximum_online_steps=64)
    assert not agent.cloned
    with pytest.raises(RuntimeError, match="Behaviour cloning must complete"):
        agent.train_offline(steps=16)
    with pytest.raises(RuntimeError, match="requires completed behaviour cloning"):
        agent.train_online(offline_env, steps=16)


def test_agent_refuses_a_non_offline_environment(offline_env):
    from api.ml.institutional.foraging_agent import ForagingAgent

    offline_env.offline = False                       # simulate a live source adapter
    with pytest.raises(ValueError, match="offline replay before live use"):
        ForagingAgent(offline_env)


def test_behaviour_cloning_requires_matured_demonstrations(offline_env):
    from api.ml.institutional.foraging_agent import BehaviourExample, ForagingAgent

    agent = ForagingAgent(offline_env, rollout_steps=16, maximum_online_steps=64)
    obs, _ = offline_env.reset(seed=3)
    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)

    def example(observed_at, label_known_at, action=0):
        return BehaviourExample(obs, action, observed_at, label_known_at, offline_env.names)

    # a label that matures after the cutoff is a look-ahead demonstration
    with pytest.raises(ValueError, match="unmatured"):
        agent.behaviour_clone([example(cutoff - timedelta(days=1), cutoff + timedelta(days=1))],
                              cutoff=cutoff, epochs=1)
    # an action naming a source the observation says is unavailable
    blocked = dict(obs)
    blocked["actions_remaining"] = np.zeros_like(obs["actions_remaining"])
    with pytest.raises(ValueError, match="unavailable source"):
        agent.behaviour_clone(
            [BehaviourExample(blocked, 1, cutoff - timedelta(days=2), cutoff - timedelta(days=1),
                              offline_env.names)],
            cutoff=cutoff, epochs=1)


def test_behaviour_cloning_trains_and_unlocks_offline_ppo(offline_env):
    from api.ml.institutional.foraging_agent import BehaviourExample, ForagingAgent

    agent = ForagingAgent(offline_env, rollout_steps=16, maximum_online_steps=64)
    obs, _ = offline_env.reset(seed=3)
    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    stop = BehaviourExample(obs, 0, cutoff - timedelta(days=2), cutoff - timedelta(days=1),
                            offline_env.names)
    stats = agent.behaviour_clone([stop] * 4, cutoff=cutoff, epochs=1, batch_size=2)
    assert agent.cloned and stats["updates"] >= 1 and np.isfinite(stats["loss"])
    agent.train_offline(steps=16)                     # the gate is now open
