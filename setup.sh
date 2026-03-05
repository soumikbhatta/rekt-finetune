#!/bin/bash
# One-time setup — creates an isolated venv, installs deps, installs Chromium.
# Nothing touches your global Python or system.
# Run from repo root: bash setup.sh

set -e

VENV=".venv"

echo "Creating virtual environment..."
python3 -m venv "$VENV"
source "$VENV/bin/activate"

echo "Installing dependencies..."
pip install --upgrade pip -q
pip install playwright beautifulsoup4 mlx-lm -q

echo "Installing Playwright Chromium browser..."
playwright install chromium

echo ""
echo "Setup complete. Virtual environment: $VENV/"
echo ""
echo "Next steps:"
echo "  1. Scrape rekt.news:      source .venv/bin/activate && python scraper/scrape_rekt.py"
echo "  2. Prepare training data: python prepare/convert_to_jsonl.py"
echo "  3. Fine-tune:             bash finetune/train.sh"
