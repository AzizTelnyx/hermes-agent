#!/usr/bin/env python3
"""Cron wrapper: run the DG Hub API rate-limit monitor.

Delegates to the canonical monitor in the demand-gen-hub repo. Prints nothing
when everything is healthy (so the cron job stays silent); prints an alert only
when a platform crosses a warning/alert threshold.
"""
import runpy
import sys

MONITOR = "/Users/azizalsinafi/.openclaw/workspace/demand-gen-hub/scripts/monitor_api_limits.py"

sys.argv = [MONITOR]  # no --always -> silent unless at risk
runpy.run_path(MONITOR, run_name="__main__")
