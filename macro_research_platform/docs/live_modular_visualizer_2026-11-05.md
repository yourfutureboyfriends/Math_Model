# Live measured neural visualizer — 5 November 2026

The Network visualizer now offers three views: interactive shallow inference, modular architecture, and live modular signal flow. The shallow export repair remains separate from the sequence network.

The live view reads actual checkpoint computations. For each seed and each prefix of the latest 24-month sequence, it records specialist encoder RMS activation, learned routing, GRU states, memory RMS, temporal attention and raw task probabilities. Attention sees only the prefix. Prefix outputs are tested against direct model inference; changing later inputs cannot alter earlier displayed outputs. The heatmap samples the first twelve GRU units and explicitly labels that sample. Routing/attention are not causal attribution.

A model checkpoint stores tensor state dictionaries plus the fitted preprocessing transform and ordered input schema. Inference reuses the saved scalers/PCA instead of refitting normalization on new inputs. Checkpoints are loaded with weights_only=True in an isolated worker. The API never imports Torch. Schema changes require rebuilding the checkpoint.

Full research training automatically exports its checkpoint and measured trace when the live fit completes. To make inspection available without waiting for a full walk-forward rebuild, the live view can build a bounded three-epoch, one-seed inspection preview. This uses real data and the modular architecture, but remains explicitly labelled a preview rather than a served or promoted model. Full checkpoints take precedence when available.

Training writes atomic telemetry updates including stage, seed, epoch, validation loss and update time. The UI polls measured state every two seconds. While the live view is open it requests input inference at most once per minute, coalesced across callers, without retraining. This is a monthly macro/market model: the publication-lagged source values do not necessarily change each minute. Input fingerprints distinguish changed from unchanged values; timestamps distinguish trained time, input as-of and inference time. Replay animates measured prefix computations; it is not a historical out-of-sample performance record.

Workers have a four-minute inspection timeout and parent-process guard. Failures retain the last measured trace. Automatic model promotion and trading behavior remain unchanged.

Validation: backend tests cover actual prefix probabilities, absence of future-prefix leakage, attention normalization, checkpoint round-trip parity, frozen transforms, detecting changed inputs, safe API imports and training telemetry. UI checks cover missing-state behavior and explicitly labelled measured previews, alongside existing visualizer arithmetic tests.

References researched before implementation:
- https://docs.pytorch.org/docs/main/generated/torch.nn.GRU.html
- https://docs.pytorch.org/docs/2.15/generated/torch.nn.modules.activation.MultiheadAttention.html
- https://docs.pytorch.org/tutorials/beginner/basics/saveloadrun_tutorial.html
- https://docs.pytorch.org/docs/stable/notes/serialization
- https://distill.pub/2018/building-blocks/
- https://distill.pub/2020/circuits/visualizing-weights/

## Animated presentation

The live view now shares the shallow visualizer's perspective panels, circular nodes, glowing signals and particle lines. Motion can be paused independently of measured sequence replay and respects system/app reduced-motion preferences. Blue edges show routing/state summaries; gold edges show temporal attention. Monthly memory states are grouped into at most twelve displayed nodes; attention weights are summed within each group. This bounds rendering to a few dozen nodes/edges rather than drawing every parameter. Animation illustrates stage flow; it does not imply new inputs arrive on every frame. Task labels sit outside incoming paths for legibility.

The full research checkpoint completed during verification and replaced the initial preview in the live view. Checkpoint inference showed unchanged input values honestly while training telemetry and timestamps continued to update.
