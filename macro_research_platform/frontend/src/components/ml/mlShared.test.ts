import { describe, expect, it } from 'vitest';
import { ensemble, forward, sigmoid, type Weights } from './mlShared';

// one input, two hidden units: h = tanh(z·W1 + b1), p = sigmoid(h·W2 + b2), z = (x − mu) / sd
const w: Weights = { mu: [1], sd: [2], nets: [
  { W1: [[1, -1]], b1: [0, 0], W2: [1, 1], b2: 0 },
  { W1: [[2, 0]], b1: [0, 0.5], W2: [1, -1], b2: 0.1 },
] };

describe('in-browser network', () => {
  it('runs the forward pass the backend exported', () => {
    const r = forward(w.nets[0], w, [3]);                      // z = 1
    expect(r.z[0]).toBeCloseTo(1);
    expect(r.h[0]).toBeCloseTo(Math.tanh(1)); expect(r.h[1]).toBeCloseTo(Math.tanh(-1));
    expect(r.p).toBeCloseTo(sigmoid(Math.tanh(1) + Math.tanh(-1)));   // = 0.5
  });
  it('averages the networks, recalibrates after pooling, and reports their range', () => {
    const raw = [forward(w.nets[0], w, [3]).p, forward(w.nets[1], w, [3]).p];
    const plain = ensemble(w, null, [3]);
    expect(plain.p).toBeCloseTo((raw[0] + raw[1]) / 2);
    expect(plain.lo).toBeCloseTo(Math.min(...raw)); expect(plain.hi).toBeCloseTo(Math.max(...raw));
    const cal = ensemble(w, [0, 0.5], [3]);                    // Platt slope 0.5 pulls towards one half
    expect(Math.abs(cal.p - 0.5)).toBeLessThan(Math.abs(plain.p - 0.5) + 1e-12);
  });
});

import {connectionSignals,selectedPrediction,validWeights} from './mlShared';
it('displays the actual linear input signal without an extra tanh',()=>{
 const s=connectionSignals(w.nets[0],w,[7]);
 expect(s.input[0][0]).toBeCloseTo(3);
 expect(s.input[0][1]).toBeCloseTo(-3);
});
it('labels a selected network output rather than the ensemble average',()=>{
 const r=selectedPrediction(w.nets[1],w,[3],[0,.5]);
 expect(r.raw).toBeCloseTo(forward(w.nets[1],w,[3]).p);
 expect(r.p).not.toBeCloseTo(ensemble(w,[0,.5],[3]).p,5);
});
it('rejects incompatible or degenerate exports',()=>{
 expect(validWeights(w,1)).toBe(true);
 expect(validWeights({...w,sd:[0]},1)).toBe(false);
 expect(validWeights(w,2)).toBe(false);
 expect(validWeights({...w,nets:[]},1)).toBe(false);
});
