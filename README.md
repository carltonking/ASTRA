# ASTRA — Autonomous Self-learning Trading and Research Agent

ASTRA (Autonomous Self-learning Trading and Research Agent) is a conversational AI system that takes a trading idea from concept to a battle-tested, exportable algorithm. Built on the AURORA methodology engine, ASTRA guides users through an 8-step research pipeline: Plan → Build → Backtest → Paper Trade → Analyze → Optimize → Graduate → Export.

```
                         ┌──────────────────────────────────────────┐
                         │           ASTRA Pipeline Loop            │
                         │                                          │
  ┌───────┐    ┌───────┐ │ ┌───────┐    ┌───────┐    ┌───────┐   │
  │ PLAN  │───▶│ BUILD │─│▶│BTEST  │───▶│PAPER  │───▶│ANALYZE│   │
  │       │    │       │ │ │       │    │TRADE  │    │(DIAG) │   │
  └───────┘    └───────┘ │ └───────┘    └───────┘    └───────┘   │
                          │     │                          │       │
                          │     │       OPTIMIZE LOOP      │       │
                          │     └──────────┐    ┌──────────┘       │
                          │               ▼    ▼                   │
                          │           ┌──────────┐                  │
                          │           │OPTIMIZE  │──────────────────┘
                          │           └──────────┘
                          │                 │
                          │                 ▼
                          │           ┌──────────┐    ┌──────────┐
                          │           │GRADUATE  │───▶│ EXPORT   │
                          │           └──────────┘    └──────────┘
                          └──────────────────────────────────────────┘
```

## Installation

```bash
git clone https://github.com/carltonking/A.S.T.R.A
cd A.S.T.R.A
pip install -e .
cd src/astra/ui/frontend && npm install && cd ../../../..
cp .env.example .env   # Add your ANTHROPIC_API_KEY and Alpaca paper keys
```

## How to Start

```bash
./src/astra/ui/start.sh
```

This launches:
- **FastAPI backend** on `http://localhost:8000`
- **React frontend** on `http://localhost:3000`

Open `http://localhost:3000` in your browser and describe your trading idea to the ASTRA chat interface.

## Methodology Engine

ASTRA's backtesting and validation pipeline is powered by [AURORA](https://github.com/carltonking/aurora-trading-research) v3.0.0 — a research methodology engine that provides CPCV (Combinatorial Purged Cross-Validation), leakage detection, and review board analysis.

![AURORA v3.0.0](https://img.shields.io/badge/AURORA-v3.0.0-blue)

## Limitations

1. Past performance does not guarantee future results
2. This strategy was validated only in specific market conditions
3. Paper trading does not account for slippage, fees, or liquidity constraints
4. Live trading may produce substantially different results
5. This certificate does not constitute financial advice

## Safety Boundaries

- **No live trading capability** — all Alpaca interactions are restricted to the paper trading API. Construction of an `AstraAlpacaClient` with a live URL raises `LiveTradingBlockedError`.
- **No short selling** — all generated strategy templates return binary signals (1 = long, 0 = no position). Short selling patterns are blocked by `BuildSandbox` and raise `ShortSellingBlockedError`.
- **No profitability claims** — every `PipelineResult`, `PerformanceSnapshot`, and `ExportPackage` carries a mandatory disclaimer.
- **RESEARCH PURPOSES ONLY** badge is permanently displayed in the UI header.
- **Export validation** — exported strategy files are validated for ASTRA independence, no network imports, no live references, and mandatory disclaimer presence before they leave the system.

## Architecture

See [docs/ASTRA_ARCHITECTURE.md](docs/ASTRA_ARCHITECTURE.md) for the complete technical architecture, module data flows, and safety invariants.
