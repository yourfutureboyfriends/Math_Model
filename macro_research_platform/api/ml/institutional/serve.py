"""Explicit deployment entry point; no scheduler starts on application import."""
from __future__ import annotations
import argparse
import importlib
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if not config.get('enabled'):
        raise SystemExit('Autonomous deployment is disabled in the configuration; no job was started.')
    reference = os.environ.get('MACRO_PIPELINE_FACTORY','')
    module,separator,function = reference.partition(':')
    if not separator or not module or not function:
        raise SystemExit('Set MACRO_PIPELINE_FACTORY=your_adapter_module:build_pipeline after wiring the required PIT/calendar/artifact adapters.')
    factory = getattr(importlib.import_module(module),function)
    from api.ml.institutional.pipeline import AutonomousDailyPipeline,prefect_flow
    pipeline = factory(config)
    if not isinstance(pipeline,AutonomousDailyPipeline):
        raise TypeError('Factory must return AutonomousDailyPipeline')
    schedule = config['schedule']
    prefect_flow(pipeline).serve(name='macro-autonomous-daily',cron=schedule['cron'],timezone=schedule['timezone'])


if __name__=='__main__': main()
