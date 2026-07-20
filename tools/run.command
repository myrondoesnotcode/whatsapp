#!/bin/bash
# Double-click this file in Finder to analyse everything in inbox/.
cd "$(dirname "$0")" || exit 1
echo "deploy TLV — WhatsApp analysis"
echo "=============================="
python3 run.py --open
echo ""
echo "Press any key to close…"
read -n 1 -s
