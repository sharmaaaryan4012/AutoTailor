#!/bin/bash
cd /Users/aaryan/recruiting
# Bypass 'source' and use the absolute venv python binary directly
/Users/aaryan/recruiting/.venv/bin/python -m src.main --limit 10 >> /Users/aaryan/recruiting/data/cron.log 2>&1
