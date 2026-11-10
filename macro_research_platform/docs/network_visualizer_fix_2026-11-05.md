# Neural visualizer repair — 5 November 2026

Research before implementation:
- PyTorch GRU documentation specifies recurrent sequence states; these cannot be represented as the exported one-hidden-layer tanh model: https://docs.pytorch.org/docs/main/generated/torch.nn.GRU.html
- Distill separates architecture, activations and attribution. A diagram's connections or routing weights do not establish causal influence: https://distill.pub/2018/building-blocks/
- The actual shallow forward pass is standardized input × W1, tanh hidden activation, then hidden × W2 and logistic output. Weight/activation distinctions follow: https://distill.pub/2020/circuits/visualizing-weights/

Confirmed issues and repairs:
1. The deep sequence rebuild was synchronous inside task computation. Cold-start visualizers waited for the entire deep walk-forward job. Completed deep results are now read without waiting; an optional shared worker runs in the background. Other models remain available.
2. The shallow visualizer has its own endpoint and background inspection fit, independent of deep or backtest jobs. Where a completed current-month task exists, it uses that task's exact exported weights/calibration. Otherwise it explicitly labels a three-seed bounded raw inspection fit on matured outcomes, distinct from served forecasts. This fallback does not claim validation skill or production status.
3. Added a separate modular architecture view, showing configured/observed encoders, routing/fusion, recurrent memory, temporal attention and task heads. Measured counts/routing appear only after completed model metadata exists. It does not invent GRU neuron activations or browser what-if inference for an unexported recurrent model.
4. Fixed the displayed input-edge signal from weight × tanh(z) to weight × z, matching inference. Edge signs describe local signals, not causal changes to the final probability.
5. The selected seed's output now belongs to that seed; ensemble averages remain in the ensemble controls. Exported scales/weights preserve precision, preventing tiny positive scales from rounding to zero. Invalid or incompatible exports are rejected before rendering.
6. Historical replay is explicitly a replay of today's fitted weights on historical inputs, not a prospective backtest. Seed counts and hidden widths come from the export.
7. Detached deep workers now terminate after their parent backend exits, preventing duplicate orphan training after restarts.

Checks cover nonblocking deep-cache reads, independence from deep/backtest jobs, finite positive exported scales, displayed connection arithmetic, selected-versus-ensemble output, incompatible exports, and configured-versus-measured modular diagrams. Browser checks include loading, switching models, replay and narrow layout.
