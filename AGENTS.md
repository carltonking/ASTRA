# ASTRA — Agent Context

## Architecture
- **Backend**: FastAPI (`src/astra/ui/backend/main.py`) on port 8000, lifespan-based startup with LLM + LSEG session
- **Frontend**: React CRA app (`src/astra/ui/frontend/`), proxy to :8000 in dev, served by FastAPI in production
- **CLI**: `astra {plan|build|run|export}` — headless pipeline orchestration
- **LLM**: Provider abstraction (`src/astra/llm/`) with Anthropic (default), OpenAI; factory via `ASTRA_LLM_PROVIDER` env var
- **Pipeline**: State machine (PLANNING→BUILDING→RUNNING→PAPER_TRADING→GRADUATED)
- **Backtest Engine**: `src/astra/backtest/` — in-process CPCV backtesting, feature engineering, metrics, replaces AURORA
- **Data**: `src/astra/data/` — `DataProvider` ABC (`provider.py`) with registry/factory (`factory.py`); built-in providers: `yfinance`, `lseg`, `polygon`, `alphavantage`; set via `StrategySpec.data_source`
- **Notifications**: `src/astra/notifications/` — `Notifier` ABC (`base.py`) with registry/factory (`factory.py`); built-in: `slack` (webhook), `email` (SMTP); auto-initialized in `PerformanceMonitoringLoop`
- **Broker**: `src/astra/broker/` — `Broker` ABC (`base.py`) with registry/factory (`factory.py`); built-in: `alpaca`, `ibkr`, `tradier`; set via `ASTRA_BROKER` env var
- **LSEG session lifecycle**: opened at app/cli startup, closed on shutdown

## Key Commands
```
uv sync --dev              # install with dev deps
uv sync --dev --extra lseg # install LSEG data support
uv run pytest tests/       # 697+ tests
uv run ruff check src/     # lint
uv run pyright src/        # type-check
astra plan "idea"          # plan a strategy
astra build spec.json      # build from spec
astra run spec.json -e     # full pipeline + export
```

## Conventions
- All API keys from env vars (`.env` / `.env.example` template)
- `from astra.llm.provider import LLMProvider` for type hints; inject, don't import SDKs directly
- `from astra.data.provider import DataProvider` / `from astra.data.factory import create_data_provider` for data sources
- `from astra.notifications.base import Notifier` / `from astra.notifications.factory import create_notifiers` for alerts
- `from astra.broker.base import Broker` / `from astra.broker.factory import create_broker` for brokers
- `BaseStrategy` ABC in templates; export module inlines a standalone copy
- AURORA is optional — `AuroraBridge` falls back to `BacktestEngine` in `src/astra/backtest/`
- Safety invariants (no real trading, no short selling) hardcoded in `BuildSandbox` and export
- Exports validated by `ExportValidator` — strips `from astra.*` imports, inlines `BaseStrategy`
- Alpaca API keys served to frontend via `GET /api/config` (auto-populates Paper Trading tab)

## Backtest Engine (`src/astra/backtest/`)
- `metrics.py` — Sharpe, DSR, max drawdown, annualized return, win rate, profit factor
- `features.py` — OHLCV → technical indicators (MA, RSI, MACD, BB, ATR, volume)
- `cpcv.py` — Combinatorial Purged Cross-Validation with multiple train/test paths
- `engine.py` — Orchestrator: data → features → signals → CPCV → review
- All methods work without AURORA installed; pipeline runs end-to-end with real metrics

## Key Commands (Updated)
```
uv sync --dev              # install with dev deps
uv sync --dev --extra lseg # install LSEG data support
uv run pytest tests/       # 697+ tests
uv run ruff check src/     # lint (all pre-existing issues, none new)
uv run pyright src/        # type-check
astra plan "idea"          # plan a strategy
astra build spec.json      # build from spec
astra run spec.json -e     # full pipeline + export
```

## Recent Changes

### Multi-Symbol Backtesting
- `compute_portfolio_returns()` in `metrics.py` — equal/custom-weighted aggregation of per-symbol returns into a single portfolio return series
- `CPCVBacktest.run_multi_symbol()` — accepts dict of signals & prices, computes portfolio returns, runs standard CPCV on the synthetic equity curve
- `BacktestEngine.run_cpcv_backtest()` auto-detects 1 vs N symbols; uses `run_multi_symbol()` for portfolios

### Transaction Costs
- `compute_returns()` accepts `transaction_cost` (per-trade fraction, e.g. 0.001 = 0.1%)
- Cost deducted on signal-change days only; constant-position periods unaffected
- `CPCVBacktest.transaction_cost` and `BacktestEngine.run_cpcv_backtest(transaction_cost=...)`
- `StrategySpec.transaction_cost` — defaults to 0.001; passed through pipeline to CPCV

### Grid Search & Walk-Forward Optimization
- `OptimizationEngine.run_grid_search()` — iterates all param combos via `itertools.product`, runs pipeline for each, returns best by Sharpe
- `OptimizationEngine.run_walk_forward_optimization()` — uses CPCV splits to evaluate param combos on train/test folds
- `_generate_param_grid()` — evenly-spaced values from parameter bounds
- `GridSearchResult` dataclass for structured output

### Paper Trading Deployment
- `PipelineRunner._deploy_to_paper()` now uses real `StrategyDeployer` with `create_broker()` (falls back to stub UUID on failure)
- `StrategyDeployer.deploy()` creates deployment + ledger directory; `run_cycle()` executes strategy signals via Broker ABC

### Error Handling & Data Quality
- `_retry()` — 3-attempt exponential backoff for yfinance data fetches
- `is_market_hours()` — checks if US equities market is open (Mon-Fri, 9:30-16:00 ET)
- `validate_market_data()` — checks for empty/NaN/short dataframes
- yfinance column names normalized to lowercase (`close`, `open`, `high`, `low`, `volume`)

### Persistent Storage (SQLite)
- `src/astra/storage.py` — `Storage` class with async-ready SQLite connection
- Tables: `sessions`, `pipeline_results`, `deployments`, `exports`
- Schema auto-created on first `connect()`; `save_session`, `get_pipeline_results`, `save_deployment`, etc.
- Configurable via `ASTRA_DB_PATH` env var (default `.astra/astra.db`)

### Risk Management Module
- `src/astra/backtest/risk.py` — Kelly criterion, fixed fraction sizing, volatility-adjusted sizing, stop-loss/take-profit

### Frontend Wired with Real Data
- `pipeline.backtest_complete` WebSocket event now includes real `cpcv_summary`, `leakage_verdict`, `review_board_status`
- Backtest tab (`Backtest.jsx`) displays actual CPCV metrics (Sharpe, DSR, overfit prob)

### Deflated Sharpe Ratio Fix
- `n_trials` clamped to minimum of 3 to avoid `stats.norm.ppf()` domain error (was returning NaN for n_trials < 3)

### Strategy Report Data Flow Fix
- `PipelineResult.cpcv_summary` and `backtest_metrics` now store all CPCV fields: `mean_sharpe`, `dsr`, `overfitting_probability`, `n_splits`, `annualized_return`, `max_drawdown`, `n_trades`, `win_rate`
- `ReportGenerator._build_content()` fixed: `backtest_return` now correctly maps to `cpcv_summary.annualized_return` instead of `backtest_metrics.mean_sharpe`
- PDF backtest table expanded with Annualized Return, Max Drawdown, Win Rate, and Total Trades rows

### Performance Monitoring Loop
- `src/astra/alpaca/monitor_loop.py` — `PerformanceMonitoringLoop` that periodically checks paper trading performance
- `check_and_optimize()` — takes snapshot, computes degradation, triggers `OptimizationEngine.run_optimization_loop()` when `triggers_optimizer` is True
- `run_continuous()` — background loop with configurable interval (default 60 min)
- `MonitoringCheckResult` dataclass with action, degradation, optimization result, snapshot

### Graduation End-to-End Tests
- 3 new integration tests in `test_graduation.py`:
  - `test_full_graduation_to_export_flow` — deploy → gate check → certificate → JSON roundtrip → save/load
  - `test_graduation_with_multiple_checks_before_passing` — multiple NOT_READY cycles before GRADUATED
  - `test_pipeline_result_summary_contains_cpcv_metrics` — verifies pipeline_result_summary has all CPCV fields

### README & CI/CD
- `README.md` — comprehensive user guide with setup, quick start, architecture table, and safety notes
- `.github/workflows/tests.yml` — GitHub Actions CI across Python 3.11/3.12/3.13 with lint, type-check, and pytest

### Hypothesis Property Tests for Backtest Engine
- `test_property.py` now has 14 new hypothesis tests covering:
  - `compute_sharpe_ratio` invariants: constant returns → 0, positive/varying → positive, scaling invariance, risk-free rate bias
  - `compute_deflated_sharpe_ratio` invariants: n_trials=1 equals Sharpe CDF, decreases with more trials, handles small n_obs
  - `compute_max_drawdown` invariants: always in [0,1], monotonic equity → 0 drawdown
  - `cpcv_split_indices` invariants: indices within [0,n_obs), no train/test overlap, expected path count
  - `compute_features` invariants: required columns always present, short data produces NaNs

### Parameterized Stress Tests (72 new tests)
- `tests/test_backtest_stress.py` — 72 parameterized tests:
  - `test_cpcv_runs_with_all_combos` — 216 combos: n_splits×n_test_splits×purge×embargo×dataset_size
  - `test_cpcv_invariants_across_sizes` — 18 combos across 3 dataset sizes
  - `test_cpcv_with_transaction_costs` — 15 combos with 5 seeds × 3 txn costs
  - `test_multi_symbol_cpcv` — 3 split values
  - `test_returns_lengths` — 5 values
  - `test_sharpe_scales_with_annual_factor` — 3 annual factors
  - `test_dsr_decreases_with_more_trials` — 4 trial counts
  - `test_sharpe_with_zero_std_returns` — 2 variants
  - `test_drawdown_bounds` — 5 input variants
  - `test_win_rate_bounds` — 4 sizes
  - `test_profit_factor_variants` — 6 compositions
  - `test_annualized_return_range` — 4 inputs
  - Edge cases: very short datasets, edge split combos, negative txn costs, multi-symbol weights

### Full Pipeline Integration Tests (6 new tests)
- `tests/test_integration_pipeline.py` — end-to-end Builder → PipelineRunner → Export:
  - `test_builder_produces_valid_strategy` — StrategyGenerator produces file with correct class name
  - `test_builder_llm_failure_falls_back_to_defaults` — LLM failure uses default params
  - `test_pipeline_runner_executes_successfully` — Full run with mock AuroraBridge, verifies CPCV metrics + WebSocket events
  - `test_pipeline_fails_on_leakage` — Leakage detection correctly blocks compromised strategies
  - `test_optimization_cycle_updates_cycle_number` — run_optimization_cycle increments correctly
  - `test_export_package_from_pipeline_result` — Full end-to-end from build → run → graduate → export

### Backend Performance Optimizations
- `cpcv.py` — Merged train/test loops into single pass (was 2 sequential loops over split_indices)
- `cpcv.py` — Replaced O(n log n) `groupby().last().sort_index()` with O(n) mean path equity for aggregate metrics
- `engine.py` — `_try_yfinance_fetch` and `_try_lseg_fetch` now use `ThreadPoolExecutor(max_workers=5)` for concurrent symbol fetching
- `engine.py` — `generate_signals` now uses `ThreadPoolExecutor(max_workers=8)` for concurrent signal generation

### API Documentation & Swagger
- All 13 FastAPI endpoints now have docstrings for OpenAPI/Swagger auto-docs at `/docs`
- `docs/EXPORT_SCHEMA.md` — complete spec of the `.astra` export format with all sections, versioning, validation rules

### WebSocket Fixes
- `websocket.py` — Replaced `asyncio.run()` anti-pattern with `new_event_loop().run_until_complete()` to avoid event loop leaks
- `runner.py` — WebSocket event `pipeline.backtest_complete` now uses correct field names (`dsr`, `overfitting_probability`) and sends `sharpe_per_path` for equity curve rendering

### Frontend Fixes
- `Backtest.jsx` — Fixed field name mismatch: `deflated_sharpe` → `dsr`, `overfit_prob` → `overfitting_probability`
- `Backtest.jsx` — Added Annualized Return and Total Trades to metrics cards
- `Backtest.jsx` — Now generates synthetic equity curves from `sharpe_per_path` instead of reading missing `equity_curves` field
- `Graduation.jsx` — Now fetches real data from `GET /api/session/{session_id}/graduation` instead of reading stale state
- `main.py` — `_trigger_build()` now initializes `GraduationTracker` with initial gate check on deployment

### Docker + Production
- `.dockerignore` — excludes `node_modules`, `__pycache__`, `.git`, `.venv`, `.astra/`, `tests/`
- `Dockerfile` — multi-stage build (node:20-slim → python:3.12-slim), non-root `appuser`, healthcheck
- `docker-compose.yml` — single service, port 8000, `.env` file, persistent volume at `/data`

### Data Provider Abstraction
- `src/astra/data/provider.py` — `DataProvider` ABC with `fetch_historical()`, `validate_data()`, `is_available()`
- `src/astra/data/factory.py` — `create_data_provider(source)`, `register_provider()`, `list_providers()`
- Built-in providers: `yfinance` (free, retry+backoff), `lseg` (wraps existing lseg_client.py), `polygon` (REST API, free tier), `alphavantage` (REST API, free tier, 12s rate limit)
- BacktestEngine `download_data()` now uses provider factory instead of hardcoded LSEG/yfinance branches
- Falls back to yfinance for any symbols that fail with the primary provider
- New env vars: `POLYGON_API_KEY`, `ALPHA_VANTAGE_API_KEY`

### Notifications Module
- `src/astra/notifications/` — self-contained module for alerting
- `base.py` — `Notifier` ABC with `send(subject, message, level)` method
- `slack.py` — `SlackNotifier` via incoming webhook, supports INFO/WARNING/ERROR/SUCCESS emojis
- `email.py` — `EmailNotifier` via SMTP with STARTTLS, configurable from/to addresses
- `factory.py` — `create_notifiers()` returns all configured notifiers; auto-initialized in `PerformanceMonitoringLoop`
- Hooked into `check_and_optimize()` — sends notifications on `RE_OPTIMIZED` (SUCCESS), `FAILED` (ERROR), and `MONITOR_ONLY` (INFO)
- New env vars: `SLACK_WEBHOOK_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `NOTIFY_FROM`, `NOTIFY_TO`

### Broker Abstraction
- `src/astra/broker/` — unified interface for multiple brokerage APIs (follows LLMProvider pattern)
- `base.py` — `Broker` ABC with dataclasses: `Account`, `Position`, `Order`, `PortfolioHistory`
- `alpaca_provider.py` — wraps `AstraAlpacaClient` into Broker ABC, backward-compatible
- `ibkr_provider.py` — `IBKRBroker` via `ib_insync`, supports account, positions, orders, bars, portfolio history
- `tradier_provider.py` — `TradierBroker` via REST API, sandbox mode by default, supports account, positions, orders, bars
- `factory.py` — `create_broker()` reads `ASTRA_BROKER` env var (default: `alpaca`)
- `StrategyDeployer` and `PerformanceMonitor` now accept `Broker` ABC instead of `AstraAlpacaClient`
- `PipelineRunner._deploy_to_paper()` uses `create_broker()` instead of direct `AstraAlpacaClient` instantiation
- New env vars: `ASTRA_BROKER`, `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_ACCOUNT_ID`, `TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID`

## Test Layout
- `tests/test_cli.py` — CLI argument parsing + command dispatch
- `tests/test_export.py` — packager, validator, report, sanitization
- `tests/test_integration.py` — end-to-end export + template rendering
- `tests/test_property.py` — hypothesis property-based tests
- `tests/test_pipeline.py` — AuroraBridge, BacktestEngine, PipelineRunner, PipelineState
- `tests/test_backtest_metrics.py` — 38 tests for Sharpe, DSR, drawdown, returns, txn costs
- `tests/test_backtest_cpcv.py` — 22 tests for split indices, single/multi-symbol CPCV
- `tests/test_backtest_features.py` — 18 tests for technical indicators
- `tests/test_backtest_engine.py` — 28 tests for full pipeline orchestration
- `tests/test_backtest_risk.py` — 18 tests for Kelly, position sizing, stop-loss/TP
- `tests/test_monitor_loop.py` — 4 tests for PerformanceMonitoringLoop (monitor-only, re-optimize, failed, metrics passthrough)
- Per-module tests: `test_planner`, `test_builder`, `test_optimizer`, `test_graduation` (3 new e2e), `test_alpaca`, `test_ui_backend`
