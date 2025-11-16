#!/bin/bash
# Install dependencies for live trading system

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies..."
pip install databento pandas numpy pytz requests

echo ""
echo "Checking VectorBT Pro..."
echo "Note: VectorBT Pro requires a license key from vectorbt.pro"
echo "If you have a license, install with: pip install vectorbtpro"
echo ""

echo "Installation complete!"
echo ""
echo "To test the live feed, run:"
echo "  source venv/bin/activate"
echo "  export DATABENTO_API_KEY='your_key_here'"
echo "  python run_live_trading.py config/live_trading_config.json --log-level DEBUG"
