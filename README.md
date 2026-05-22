# ASTRA — Automated Strategy Trading & Research Agent

[![Tests](https://github.com/carltonking/ASTRA/actions/workflows/tests.yml/badge.svg)](https://github.com/carltonking/ASTRA/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

ASTRA is an end-to-end trading strategy research platform. It plans, builds, backtests, optimizes, paper trades, and exports algorithmic trading strategies — all from a natural language idea.

```
User Idea → Planner → Builder → Backtest → Paper Trade → Graduate → Export
                     ↑                          ↓
                AI Optimizer ← Performance Monitor
```

## Quick Start

```bash
git clone <repo>
cd astra
uv sync --dev
cp .env.example .env
# Set at least ANTHROPIC_API_KEY or OPENAI_API_KEY in .env

# Plan a strategy from a natural language idea
astra plan "A mean reversion strategy on SPY using RSI"

# Build from a spec file
astra build spec.json

# Full pipeline with export
astra run spec.json -e

# Launch the web UI
uv run uvicorn src.astra.ui.backend.main:app --port 8000
```

Then open `http://localhost:8000`.

## Features

| Module | Purpose |
|--------|---------|
| `astra.planner` | Conversational strategy planner (LLM-powered) |
| `astra.builder` | Strategy code generator + sandbox validation |
| `astra.pipeline` | Pipeline orchestrator with leakage detection, review board, paper deployment |
| `astra.backtest` | In-process CPCV backtesting engine |
| `astra.optimizer` | Grid search, walk-forward optimization, degradation diagnosis |
| `astra.graduation` | Gate checks, certificates, standalone exports |
| `astra.storage` | SQLite persistent storage with schema migrations |

### Backtest Engine

- **CPCV** — Combinatorial Purged Cross-Validation with purge/embargo
- **Multi-Symbol** — Portfolio return aggregation for N-symbol strategies
- **Transaction Costs** — Per-trade fraction deducted on signal-change days
- **Metrics** — Sharpe, Deflated Sharpe, max drawdown, win rate, profit factor, annualized return
- **Features** — SMA, EMA, RSI, MACD, Bollinger Bands, ATR, volume indicators
- **Risk Management** — Kelly criterion, volatility-adjusted sizing, stop-loss/take-profit, VaR/CVaR, correlation-adjusted sizing
- **Leakage Detection** — Forward-looking bias check
- **Review Board** — Rule-based quality evaluation (score 0–100)

### Strategy Templates

| Type | Description |
|------|-------------|
| Trend Following | MA crossover with threshold |
| Mean Reversion | RSI-based overbought/oversold |
| Momentum | Lookback return + holding period |
| Breakout | Price breakout + volume confirmation |
| Pairs Trading | Z-score mean reversion on spread |
| DCA | Dollar-cost averaging schedule |
| Statistical Arbitrage | Cointegration spread with z-score entries |
| VWAP Momentum | VWAP proximity + momentum filter |

### Data Providers

Built-in, swappable via `StrategySpec.data_source`:

| Provider | Requires | Notes |
|----------|----------|-------|
| yfinance | Nothing | Free, automatic fallback |
| LSEG | Desktop app + `uv sync --extra lseg` | Primary for institutional data |
| Polygon.io | `POLYGON_API_KEY` | REST API, free tier |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | REST API, 12s rate limit |

### Broker Integration

Unified broker abstraction via `ASTRA_BROKER` env var (default: `alpaca`):

| Broker | Requires |
|--------|----------|
| Alpaca | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` |
| IBKR | `ib_insync` (`uv sync --extra ibkr`) |
| Tradier | `TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID` |

### Web UI

React dashboard with 7 tabs: Overview, Planner, Backtest, Optimization, Paper Trading, Graduation, Comparison. Features real-time WebSocket progress, market hours indicator, reorderable tabs, parameter presets, and strategy comparison charts.

### Notifications

Slack webhook and SMTP email alerts automatically wired into the performance monitoring loop.

### Deployment

- Docker multi-stage build with healthcheck
- Docker Compose single-service setup
- Terraform module for AWS ECS Fargate

## Testing

```bash
uv run pytest tests/        # 697+ tests
uv run ruff check src/      # lint
uv run pyright src/         # type-check
```

## API Keys (`.env`)

```
ANTHROPIC_API_KEY=sk-...           # LLM (Anthropic, default)
OPENAI_API_KEY=sk-...              # LLM (OpenAI, set ASTRA_LLM_PROVIDER=openai)
APCA_API_KEY_ID=...                # Alpaca paper trading
APCA_API_SECRET_KEY=...            # Alpaca paper trading
POLYGON_API_KEY=...                # Polygon.io data (optional)
ALPHA_VANTAGE_API_KEY=...          # Alpha Vantage data (optional)
SLACK_WEBHOOK_URL=...              # Notifications (optional)
SMTP_HOST=smtp.gmail.com           # Email notifications (optional)
```

Full template in `.env.example`.

## Safety

ASTRA enforces:
- **No live trading** — all Alpaca endpoints hard-blocked to paper API
- **No short selling** — sell orders require existing long position
- **Sandbox validation** — generated strategies scanned for dangerous imports
- **Export isolation** — standalone exports strip all internal imports

## License

MIT — see [LICENSE](LICENSE).
