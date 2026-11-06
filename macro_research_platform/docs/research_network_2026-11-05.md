# Financial research network

Open ML → Network visualizer → Research network. The existing shallow, modular architecture and live modular flow views remain available.

The initial network uses real application metadata and saved evidence: five source groups, 22 declared features, five specialist modules, the sequence architecture, six forecast tasks, available saved research-head outputs, the evaluation workflow and five reviewed paper references. With the current full research checkpoint this produces 51 nodes and 110 links. Missing checkpoints do not create fictitious probabilities or routing measurements.

Search and category filters retain immediate evidence neighbors. Clicking a node or using the keyboard-accessible inspector shows descriptions, source/paper/code links, timestamps, input digests, label-availability delays and connected evidence. Focus isolates a neighborhood. Pan, zoom, reset and optional update transitions support exploration. There is no force simulation or fabricated continuous neural activity. Fixed positions, memoized filtering and the existing shared canvas engine keep rendering work bounded for this initial graph. Refresh is scheduled every 30 seconds under the existing query client's online/visibility rules.

Dashed links describe declared provenance, task inputs, architecture or research references. Solid links describe saved routing measurements or saved outputs. Routing weights are averaged over available saved seeds; they are not causal attribution. Saved head probabilities are raw research values, not calibrated production forecasts or historical out-of-sample results. Paper connections do not claim their algorithms are installed.

The read-only authenticated `/api/v1/ml/research/graph` endpoint reads local state. It does not fetch providers, start a training run or import Torch. Stable content revisions let clients distinguish evidence changes from observation timestamps. External evidence links accept HTTPS only.

This is the first connected evidence layer. Company relationships, document ingestion, extracted claims and document-level citations are not yet connected. Those require source-specific provenance and access handling rather than decorative nodes.

Validation: two backend graph tests, five frontend tests and frontend type checking passed. Browser checks verified the authenticated graph, saved full-model evidence, paper/code links, focused neighborhoods, empty searches and narrow/wide layouts. Screenshot: `images/research-network-2026-11-05.png`.
