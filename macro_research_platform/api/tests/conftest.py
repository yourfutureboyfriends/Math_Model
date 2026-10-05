"""Unit tests run without live FRED by default.

A full run fires hundreds of FRED requests; FRED answers bursts with 429/403 and then
blocks the IP, which took the running platform's data offline. Tests that need FRED skip
without a key. Set MACRO_LIVE_FRED=1 to run them against the real API.
"""
import os

if os.environ.get("MACRO_LIVE_FRED") != "1":
    os.environ["FRED_API_KEY"] = ""
