"""Synthetic, no-network interface check; not financial performance evidence."""
from __future__ import annotations
import json
import torch
from api.ml.institutional.model import ModelConfig
from api.ml.institutional.training import TrainableMacroSystem


def main() -> None:
    torch.set_num_threads(2)
    torch.manual_seed(7)
    cfg = ModelConfig()
    model = TrainableMacroSystem(cfg,('binary',)*6)
    batch = {'specialists':torch.randn(2,24,cfg.domains,cfg.domain_inputs),
             'graph_nodes':torch.randn(2,51,cfg.graph_inputs),
             'edge_index':torch.stack([torch.arange(50),torch.arange(1,51)]),
             'edge_weight':torch.ones(50),
             'known_future':torch.randn(2,12,cfg.known_future_inputs),
             'target':torch.randint(0,2,(2,4,6)).float(),'known':torch.ones(2,4,6,dtype=torch.bool)}
    optimizer = torch.optim.AdamW(model.parameters(),lr=.001)
    for _ in range(2):
        optimizer.zero_grad(set_to_none=True)
        loss = model.loss(batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
        optimizer.step()
    model.eval()
    with torch.no_grad(): result = model.predict(batch)
    print(json.dumps({'synthetic_only':True,'graph_nodes':51,'specialists':cfg.domains,
                      'forecast_shape':list(result['predictions'].shape),'finite':bool(torch.isfinite(result['predictions']).all()),
                      'parameters':sum(p.numel() for p in model.parameters()),'training_steps':2}))


if __name__=='__main__': main()
