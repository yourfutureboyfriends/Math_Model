"""Fixed-reference drift diagnostics; reference bins are never fitted on the test window."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import hashlib
import json


@dataclass(frozen=True)
class DriftResult:
    ready: bool
    psi: list[float]
    js: list[float]
    trigger: bool
    consecutive: int


class DistributionMonitor:
    """Quantile-bin PSI/JSD with explicit missing bin and consecutive-window gate.

    Supply distinct non-overlapping window IDs. Thresholds require calibration
    on benign historical windows; drift alone is not evidence of forecast error.
    Use a separate instance for attention vectors with a fixed model/schema ID.
    """
    def __init__(self, reference: np.ndarray, *, bins: int = 10, min_rows: int = 64,
                 psi_threshold: float = .25, js_threshold: float = .1, patience: int = 3) -> None:
        x = np.asarray(reference,dtype=float)
        if x.ndim!=2 or len(x)<min_rows or bins<2 or patience<1 or np.isinf(x).any():
            raise ValueError('Invalid drift reference')
        self.reference_digest = hashlib.sha256(np.nan_to_num(x).tobytes()+np.isnan(x).tobytes()+json.dumps({'shape':x.shape,'bins':bins,'minimum':min_rows,'psi':psi_threshold,'js':js_threshold,'patience':patience},sort_keys=True).encode()).hexdigest()
        self.minimum,self.psi_threshold,self.js_threshold,self.patience = min_rows,psi_threshold,js_threshold,patience
        self.edges = []
        for column in x.T:
            finite = column[np.isfinite(column)]
            inside = np.unique(np.quantile(finite,np.linspace(0,1,bins+1)[1:-1])) if len(finite) else np.array([])
            self.edges.append(np.r_[-np.inf,inside,np.inf])
        self.reference = [self._distribution(x[:,i],edge) for i,edge in enumerate(self.edges)]
        self.consecutive,self.last_window = 0,None

    @staticmethod
    def _distribution(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
        finite = np.isfinite(x)
        counts = np.r_[np.histogram(x[finite],edges)[0],(~finite).sum()].astype(float)+.5
        return counts/counts.sum()

    def update(self, current: np.ndarray, *, window_id: str) -> DriftResult:
        if not window_id: raise ValueError('A stable monitoring window ID is required')
        x = np.asarray(current,dtype=float)
        if x.ndim!=2 or x.shape[1]!=len(self.edges) or np.isinf(x).any():
            raise ValueError('Drift schema changed or invalid inputs')
        if len(x)<self.minimum:
            return DriftResult(False,[],[],False,self.consecutive)
        psi,js = [],[]
        for i,(edges,p) in enumerate(zip(self.edges,self.reference)):
            q = self._distribution(x[:,i],edges)
            m = (p+q)/2
            psi.append(float(np.sum((q-p)*np.log(q/p))))
            js.append(float(.5*np.sum(p*np.log2(p/m))+.5*np.sum(q*np.log2(q/m))))
        breached = max(psi)>self.psi_threshold or max(js)>self.js_threshold
        if window_id!=self.last_window:
            self.consecutive = self.consecutive+1 if breached else 0
            self.last_window = window_id
        return DriftResult(True,psi,js,breached and self.consecutive>=self.patience,self.consecutive)

    def state_dict(self) -> dict:
        return {'consecutive':self.consecutive,'last_window':self.last_window}

    def load_state_dict(self, state: dict) -> None:
        self.consecutive,self.last_window = int(state['consecutive']),state['last_window']
