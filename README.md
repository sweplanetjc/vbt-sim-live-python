## Repository Structure

- **Core Application:** `scanner/`, `execution/`, `strategies/`, `indicators/`, `vbt_sim_live/`
- **Entry Points:** `run_live_trading.py`
- **Development Tools:** `scripts/` - backtesting, data fetching, debugging, monitoring
- **Tests:** `tests/unit/`, `tests/integration/`
- **Documentation:** `Docs/` - architecture, workflows, API reference
- **Configuration:** `config/live_trading_config.json`, `.env`

**Quick Start:**
```bash
# Setup
cp .env.example .env  # Add your API keys
pip install -r requirements.txt

# Run live trading (dry run)
python run_live_trading.py config/live_trading_config.json

# Run tests
pytest tests/ -v
```

**Documentation:** See [Docs/README.md](Docs/README.md) for comprehensive documentation.
