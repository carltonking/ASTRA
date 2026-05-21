# ASTRA Architecture

## Overview

ASTRA is composed of 8 modules arranged in a linear pipeline with an optimization feedback loop. Data flows strictly forward through the pipeline; the optimizer loop feeds back into the build step with updated parameters. The WebSocket event bus bridges every pipeline event to the UI in real time.

```
                         ┌─────────────────────────────────────────────┐
                         │              WebSocket Event Bus            │
                         │  broadcast( event, data ) → all clients     │
                         └──────────┬──────────┬──────────┬────────────┘
                                    │          │          │
   ┌───────┐   ┌───────┐   ┌───────┴──┐  ┌────┴────┐  ┌──┴─────────┐
   │Planner│──▶│Builder│──▶│ Pipeline │──▶│ Alpaca  │──▶│ Optimizer  │──┐
   │(Spec) │   │(Code) │   │(AURORA)  │  │(Paper)  │  │(Diagnosis) │  │
   └───────┘   └───────┘   └──────────┘  └─────────┘  └────────────┘  │
        │           │            │             │              ▲        │
        │           │            │             │              │        │
        ▼           ▼            ▼             ▼              │        │
   ┌──────────────────────────────────────────────────────────┘        │
   │                    SessionStore (in-memory + disk)                 │
   └───────────────────────────────────────────────────────────────────┘
        │
        ▼
   ┌──────────┐   ┌──────────┐   ┌──────┐
   │Graduation│──▶│  Export  │──▶│  UI  │
   │(Gates)   │   │(.py+PDF) │   │React │
   └──────────┘   └──────────┘   └──────┘
```

## Data Flow

Each module produces a well-defined data object consumed by the next:

| Module | Produces | Consumes | Description |
|--------|----------|----------|-------------|
| **Planner** | `StrategySpec` | user idea (text) | Complete strategy specification from Claude dialogue |
| **Builder** | `BuildResult` | `StrategySpec` | Generated Python strategy file + validated parameters |
| **Pipeline** | `PipelineResult` | `BuildResult`, `StrategySpec` | AURORA backtest metrics, CPCV results, leakage/review verdicts |
| **Alpaca** | `PerformanceSnapshot` | `Deployment` | Real-time paper trading performance metrics (Sharpe, return, drawdown, win rate) |
| **Optimizer** | `ParameterProposal` | `Diagnosis`, `PerformanceSnapshot` | Parameter change recommendations or strategy rebuild decisions |
| **Graduation** | `GraduationCertificate` | `GateCheckResult` | Immutable certificate when all 6 gates pass |
| **Export** | `ExportPackage` | `GraduationCertificate`, `BuildResult` | Self-contained .py file + PDF report |
| **UI** | — | all of the above (via REST + WebSocket) | FastAPI backend + React frontend |

```
StrategySpec  ──▶  BuildResult  ──▶  PipelineResult  ──▶  PerformanceSnapshot
     │                                                          │
     │                                                          ▼
     │                                                   GateCheckResult
     │                                                          │
     │                                                          ▼
     └───────────────────▶  GraduationCertificate  ──▶  ExportPackage
```

## Module Interfaces

### Planner (`src/astra/planner/`)

- `StrategySpec` — dataclass with 24 fields (asset_class, symbols, timeframe, entry/exit conditions, position sizing, etc.), JSON serializable, completeness tracking
- `PlannerConversation(anthropic_api_key)` — Claude sonnet-4 dialogue, 8-question sequence, detects `SPEC_READY`/`SPEC_REJECTED`
- `SpecValidator` — validates position sizing (0.01–1.0), return/drawdown reasonableness, backtest period logic

### Builder (`src/astra/builder/`)

- `BaseStrategy` — ABC with `generate_signals(data: pd.DataFrame) → pd.Series` and `get_parameters()`
- 6 templates: trend_following, mean_reversion, momentum, pairs, breakout, DCA
- `StrategyGenerator(api_key, build_dir)` — two-phase generation: Claude infers parameters → template fill → sandbox validation → fallback to defaults on failure
- `BuildSandbox` — AST-based analysis: blocks network imports (`requests`, `urllib`, `socket`), `eval()`/`exec()`, short selling patterns (`side="sell"`, `qty < 0`)
- `AuroraConfigWriter` — produces AURORA-compatible YAML config (no pyyaml dependency)

### Pipeline (`src/astra/pipeline/`)

- `PipelineRunner` — orchestrates: data download → leakage detection → feature engineering → signal generation → CPCV backtest → review board → paper deploy
- `AuroraBridge` — stub wrapper around AURORA engine, graceful fallback when not installed
- `PipelineState` — session state machine with valid status transitions (PLANNING → BUILDING → RUNNING → OPTIMIZING → PAPER_TRADING → GRADUATED / FAILED / ABANDONED)
- `PipelineEventBus` — publish/subscribe for real-time events, history buffer for late WebSocket connections

### Alpaca (`src/astra/alpaca/`)

- `AstraAlpacaClient` — lazy-loads alpaca-py, validates paper URL at construction, raises `LiveTradingBlockedError` for live URLs
- `StrategyDeployer` — dynamic strategy import → bar fetch → signal computation → position reconciliation → order submission
- `PerformanceMonitor` — computes Sharpe, annualized return, max drawdown, win rate from portfolio history
- `DegradationReport` — `compute_degradation()` compares paper vs backtest, returns ACCEPTABLE/ELEVATED/SEVERE

### Optimizer (`src/astra/optimizer/`)

- `DiagnosisEngine` — deterministic pattern matching (no AI): INSUFFICIENT_DATA, PARAMETER_SENSITIVITY, TRANSACTION_COST_DRAG, POSITION_SIZING, SIGNAL_DECAY
- `ParameterProposer` — Claude for ADJUST_PARAMETERS, short-circuits for EXTEND_OBSERVATION/REBUILD_STRATEGY/ABANDON
- `OptimizationEngine` — loop: snapshot → diagnose → propose → pipeline cycle, stops on ABANDON/EXHAUSTED/ERROR
- `OptimizationHistory` — cycling detection, improvement tracking, save/load

### Graduation (`src/astra/graduation/`)

- `GraduationGates` — 6 configurable thresholds (DSR ≥ 1.5, return ≥ 5%, drawdown ≤ 20%, trades ≥ 20, degradation ≤ 0.2, days ≥ 5), env/config override
- `GateCheckResult` — `overall_status: GRADUATED | NOT_READY`, individual `GateResult` per gate with gap and evidence
- `GraduationCertificate` — immutable, exactly 5 limitations, `from_gate_check()` raises if not GRADUATED
- `GraduationTracker` — per-cycle history, `issue_certificate()` mints certificate, `save()`/`load()` for persistence

### Export (`src/astra/export/`)

- `StrategyPackager(export_dir)` — reads original strategy code, prepends certificate header + metadata dict + risk limits + docstring, compute SHA256 checksum
- `ExportValidator` — final safety checks: valid Python (ast.parse), no ASTRA imports, no network imports, no live references, certificate header + STRATEGY_METADATA + disclaimer + limitations present
- `ReportGenerator(export_dir)` — 6-page PDF with reportlab (cover, strategy summary, performance evidence, methodology, gates, limitations), fallback to plaintext if reportlab unavailable
- `ExportPackage` — dataclass with export_id, checksum, paths, disclaimer

### UI (`src/astra/ui/`)

- **Backend**: FastAPI with 10 REST endpoints + WebSocket endpoint, injectable dependencies for testing
- **SessionStore**: in-memory dict with JSON save/load, stores PipelineState + conversation + deployment + tracker + history
- **WebSocketManager**: connects PipelineEventBus to frontend, sends full event history on connect, broadcast to all connected clients
- **Frontend**: React 18 with recharts, two-panel layout (40% chat / 60% dashboard), 5 dashboard tabs, auto-reconnecting WebSocket hook

## Safety Boundaries (Architectural Invariants)

1. **No live trading**: `AstraAlpacaClient.__init__` validates URL prefix — `https://api.alpaca.markets` raises `LiveTradingBlockedError`. Only `https://paper-api.alpaca.markets` is accepted.
2. **No short selling**: `BuildSandbox` scans for `side="sell"`, negative quantities, `short` patterns. `StrategyDeployer.run_cycle` only submits buy/close orders. Short selling raises `ShortSellingBlockedError`.
3. **No profitability claims**: Every result dataclass (`PipelineResult`, `PerformanceSnapshot`, `OptimizationResult`, `ExportPackage`) carries a mandatory `disclaimer` field. The UI permanently displays "RESEARCH PURPOSES ONLY" in header and footer.
4. **Self-contained exports**: `ExportValidator` ensures exported .py files have no ASTRA imports, no network imports, and include the full disclaimer and limitations.
5. **Certificate immutability**: `GraduationCertificate.limitations` is set to the canonical 5 items at construction and never modified. `GraduationTracker.issue_certificate()` raises if a certificate already exists for the session.
6. **Alpaca key isolation**: Alpaca API keys are read from environment variables and never logged, serialized to disk, or exposed via API responses.
7. **Deterministic optimization diagnosis**: The diagnosis engine uses only threshold-based pattern matching — no AI involved in optimization decisions, ensuring reproducibility.

## External Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| **Claude API** (Anthropic) | sonnet-4-20250514 | Strategy planning conversation, parameter inference, optimization proposals |
| **Alpaca Paper API** | — | Paper trading execution, portfolio history, positions, orders |
| **AURORA** | v3.0.0 (git) | CPCV backtesting, leakage detection, feature engineering, review board |
| **reportlab** | ≥ 4.0.0 | PDF report generation |
| **FastAPI** | ≥ 0.110.0 | REST API + WebSocket server |
| **yfinance** | ≥ 0.2.0 | Free market data source for backtests |

The system degrades gracefully when AURORA is not installed — the pipeline runner returns a descriptive error rather than crashing.
