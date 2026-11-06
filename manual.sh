#!/bin/bash
set -e

# Navigate to project root
cd "$(dirname "$0")"

INPUT_FILE="${1:-manual_input.txt}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "[AutoTailor] Error: Input file '$INPUT_FILE' not found."
    echo "Creating a template '$INPUT_FILE' for you..."
    cat << 'EOF' > "$INPUT_FILE"
# ==============================================================================
# AutoTailor Manual Input
#
# Instructions:
# 1. (Optional) You can fill in the headers below, or leave them blank.
#    If blank, Gemini will automatically detect the Company and Role Title!
# 2. Paste the full job description below the separator line (---).
# 3. Save this file and run: ./manual.sh
# ==============================================================================
Company: 
Role: 
Keywords: 
Track: 
URL: 
---
[Paste job description from the internet here]
EOF
    echo "Template created at '$INPUT_FILE'. Paste your job description and re-run ./manual.sh"
    exit 1
fi

echo "[AutoTailor] Processing manual job from '$INPUT_FILE'..."
/Users/aaryan/recruiting/.venv/bin/python -m src.manual --from-file "$INPUT_FILE"

