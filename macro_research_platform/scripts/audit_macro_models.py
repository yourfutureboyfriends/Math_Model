"""Run the three research macro views and save a data-readiness audit. Does not stage orders."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api.model.engine import run_model
from api.model.economies import ECONOMIES

async def main():
    rows=[]
    for economy in ECONOMIES:
        print('Running '+economy,flush=True)
        try:
            result=await run_model(persist=False,force=True,economy=economy)
            rows.append(result)
            print(json.dumps({'economy':economy,'available':result.get('available'),'reason':result.get('reason'),'as_of':result.get('as_of'),'quality':result.get('data_quality'),'backtest_available':result.get('backtest',{}).get('available'),'backtest_reason':result.get('backtest',{}).get('reason')},default=str),flush=True)
        except Exception as exc:
            rows.append({'economy':{'id':economy},'available':False,'reason':f'{type(exc).__name__}: {exc}'})
            print(economy+' failed: '+str(exc),flush=True)
    out=ROOT/'data/processed/macro_audit_2026-10-31.json'
    out.write_text(json.dumps({'run_at':datetime.now(timezone.utc).isoformat(),'models':rows},indent=2,default=str,allow_nan=False))
    print('Saved '+str(out),flush=True)

if __name__=='__main__':asyncio.run(main())
