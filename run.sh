#!/bin/bash
set -e

# Navigate to the project root directory
cd "$(dirname "$0")"

# Source the Python virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Execute the pipeline and append output to data/cron.log
mkdir -p data
python3 -m src.main --limit 10 >> data/cron.log 2>&1
