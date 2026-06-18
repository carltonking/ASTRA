"""Tools the unified finance assistant can call.

Each tool is a plain function taking a ToolContext (duck-typed to avoid a circular
import with tool_dispatcher) plus validated kwargs, returning a token-SMALL dict.
Outputs are summaries/stats — never raw OHLCV — to keep the model's context lean.
"""

import asyncio
import concurrent.futures
import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from astra.builder.templates import (
    TEMPLATES_BY_TYPE,
    DEFAULT_PARAMETERS_BY_TYPE,
    CLASS_NAME_BY_TYPE,
)
from astra.planner.spec import StrategySpec
from astra.backtest.metrics import (
    compute_returns,
    compute_portfolio_returns,
    compute_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
    compute_win_rate,
)

# One-line descriptions + typical use, for list_algorithms (static knowledge).
_ALGO_INFO = {
    "trend_following": ("Dual moving-average crossover; rides sustained directional moves.", "trending markets, low-to-normal volatility"),
    "mean_reversion": ("RSI extremes; fades short-term overextensions.", "range-bound, mean-reverting markets"),
    "momentum": ("Lookback-return persistence; buys recent strength.", "persistent trends, risk-on regimes"),
    "pairs": ("Ratio z-score on two legs; relative-value, market-neutral.", "cointegrated pairs, any regime"),
    "breakout": ("Range breakout with volume confirmation.", "volatility expansion, new trends"),
    "dca": ("Scheduled dollar-cost averaging; passive accumulation.", "long-horizon accumulation"),
    "stat_arb": ("Hedge-ratio spread mean reversion across two legs.", "cointegrated pairs, neutral exposure"),
    "vwap_momentum": ("VWAP-anchored volume-weighted momentum.", "intraday/volume-driven momentum"),
}

# Algorithms that need two legs / special data shape — unsupported in quick_backtest.
_TWO_LEG_ALGOS = {"pairs", "stat_arb"}

_PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 182, "1y": 365, "2y": 730, "5y": 1825}

# JSON-schema tool declarations consumed by provider.generate_with_tools.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_algorithms",
        "description": "List ASTRA's eight built-in algorithm templates with descriptions, default parameters, bounds, and typical use. Call this to ground any algorithm recommendation.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_market_data",
        "description": "Fetch summary statistics (return, volatility, max drawdown, recent trend) for one or more tickers over a period. Use for any factual claim about a symbol's recent behaviour. Returns stats only, not raw prices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "1-5 tickers, e.g. ['SPY','QQQ']"},
                "period": {"type": "string", "enum": list(_PERIOD_DAYS.keys()), "description": "Lookback window"},
                "data_source": {"type": "string", "enum": ["yfinance", "polygon", "alphavantage", "lseg"], "description": "Default yfinance"},
            },
            "required": ["symbols", "period"],
        },
    },
    {
        "name": "quick_backtest",
        "description": "Run a fast, indicative single-asset backtest of one algorithm template on a symbol over a period. Returns Sharpe, return, max drawdown, trade count. No purged cross-validation — indicative only. Does NOT support pairs/stat_arb.",
        "input_schema": {
            "type": "object",
            "properties": {
                "algorithm": {"type": "string", "enum": list(TEMPLATES_BY_TYPE.keys())},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "1-5 tickers"},
                "period": {"type": "string", "enum": list(_PERIOD_DAYS.keys())},
                "data_source": {"type": "string", "enum": ["yfinance", "polygon", "alphavantage", "lseg"]},
                "param_overrides": {"type": "object", "description": "Optional parameter overrides; defaults used otherwise"},
            },
            "required": ["algorithm", "symbols", "period"],
        },
    },
    {
        "name": "search_memory",
        "description": "Search ASTRA's research memory for insights from past strategy validations (which approaches passed/failed and how robust they were).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 5"},
                "min_robustness": {"type": "number", "description": "0-1 floor, default 0"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "build_strategy",
        "description": "Build and validate a strategy from a finalized spec. Call ONLY after the user explicitly confirms they want to build. Triggers a real build-and-backtest pipeline. Provide every required field.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_class": {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "timeframe": {"type": "string"},
                "data_source": {"type": "string", "enum": ["yfinance", "lseg"]},
                "strategy_type": {"type": "string", "enum": list(TEMPLATES_BY_TYPE.keys())},
                "market_hypothesis": {"type": "string"},
                "entry_conditions": {"type": "array", "items": {"type": "string"}},
                "exit_conditions": {"type": "array", "items": {"type": "string"}},
                "target_return": {"type": "number", "description": "Annual target as fraction, e.g. 0.15"},
                "max_drawdown": {"type": "number", "description": "Max acceptable drawdown fraction, e.g. 0.20"},
                "position_size": {"type": "number", "description": "Fraction of capital per position"},
                "max_positions": {"type": "integer"},
                "backtest_start": {"type": "string", "description": "YYYY-MM-DD"},
                "backtest_end": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": [
                "asset_class", "symbols", "timeframe", "data_source", "strategy_type",
                "market_hypothesis", "entry_conditions", "exit_conditions", "target_return",
                "max_drawdown", "position_size", "max_positions", "backtest_start", "backtest_end",
            ],
        },
    },
]


def run_async(coro) -> Any:
    """Run a coroutine to completion from a synchronous tool.

    The assistant loop runs off the FastAPI event loop (via asyncio.to_thread), so
    this worker thread has no running loop and asyncio.run is safe. We still guard
    by spawning a fresh thread if a loop happens to be running here.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _period_to_dates(period: str) -> tuple[str, str]:
    days = _PERIOD_DAYS.get(period, 365)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _coerce_params(algo: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge defaults with overrides, coercing override types to match defaults."""
    params = dict(DEFAULT_PARAMETERS_BY_TYPE.get(algo, {}))
    for k, v in (overrides or {}).items():
        if k in params:
            try:
                params[k] = type(params[k])(v)
            except (TypeError, ValueError):
                pass
    return params


def instantiate_template(algo: str, params: dict[str, Any]):
    """Build a strategy instance in memory from a template — no disk, no LLM."""
    template = TEMPLATES_BY_TYPE[algo]
    code = template.format(hypothesis="quick_backtest", **params)
    namespace: dict[str, Any] = {}
    exec(code, namespace)  # noqa: S102 - trusted, repo-owned template strings
    cls = namespace[CLASS_NAME_BY_TYPE[algo]]
    return cls(**params)


# --- Tools ---


def list_algorithms(ctx: Any) -> dict[str, Any]:
    algos = []
    for algo, template in TEMPLATES_BY_TYPE.items():
        desc, typical = _ALGO_INFO.get(algo, ("", ""))
        defaults = DEFAULT_PARAMETERS_BY_TYPE.get(algo, {})
        try:
            bounds = instantiate_template(algo, defaults).get_parameter_bounds()
        except Exception:
            bounds = {}
        algos.append({
            "type": algo,
            "description": desc,
            "default_params": defaults,
            "param_bounds": {k: list(v) for k, v in bounds.items()},
            "typical_use": typical,
        })
    return {"algorithms": algos}


def _symbol_stats(symbol: str, df) -> dict[str, Any]:
    close = df["close"].dropna()
    if len(close) < 2:
        return {"symbol": symbol, "error": "insufficient data"}
    rets = close.pct_change().dropna()
    equity = (1 + rets).cumprod()
    ann_vol = float(rets.std() * (252 ** 0.5) * 100)
    total_ret = float((close.iloc[-1] / close.iloc[0] - 1) * 100)
    max_dd = float(compute_max_drawdown(equity) * 100)
    recent = close.tail(20)
    trend = "flat"
    if len(recent) >= 2:
        slope = float(recent.iloc[-1] - recent.iloc[0])
        trend = "up" if slope > 0 else ("down" if slope < 0 else "flat")
    return {
        "symbol": symbol,
        "n_bars": int(len(close)),
        "last_close": round(float(close.iloc[-1]), 2),
        "total_return_pct": round(total_ret, 2),
        "annualized_vol_pct": round(ann_vol, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "recent_trend": trend,
    }


def get_market_data(ctx: Any, symbols: list[str], period: str, data_source: str = "yfinance") -> dict[str, Any]:
    symbols = [s.upper() for s in symbols][:5]
    start, end = _period_to_dates(period)
    data_key = ctx.engine.download_data(symbols, start, end, data_source)
    data = ctx.engine.get_cached_data(data_key) or {}
    out = []
    for s in symbols:
        if s in data:
            out.append(_symbol_stats(s, data[s]))
        else:
            out.append({"symbol": s, "error": "no data"})
    return {"period": period, "data_source": data_source, "symbols": out}


def quick_backtest(
    ctx: Any,
    algorithm: str,
    symbols: list[str],
    period: str,
    data_source: str = "yfinance",
    param_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if algorithm not in TEMPLATES_BY_TYPE:
        return {"error": f"unknown algorithm '{algorithm}'"}
    if algorithm in _TWO_LEG_ALGOS:
        return {"error": f"{algorithm} needs two cointegrated legs and isn't supported in quick_backtest; use build_strategy instead"}

    symbols = [s.upper() for s in symbols][:5]
    params = _coerce_params(algorithm, param_overrides)
    start, end = _period_to_dates(period)

    data_key = ctx.engine.download_data(symbols, start, end, data_source)
    feat_key = ctx.engine.build_features(data_key)
    features = ctx.engine.get_cached_features(feat_key) or {}
    if not features:
        return {"error": "no data available for backtest"}

    strat = instantiate_template(algorithm, params)
    signals = {sym: strat.generate_signals(fdf) for sym, fdf in features.items()}

    if len(features) == 1:
        sym, fdf = next(iter(features.items()))
        rets = compute_returns(signals[sym], fdf["close"], transaction_cost=0.001)
    else:
        prices = {s: fdf["close"] for s, fdf in features.items()}
        rets = compute_portfolio_returns(signals, prices, transaction_cost=0.001)

    if rets is None or len(rets) < 2:
        return {"error": "backtest produced no returns (no trades / insufficient data)"}

    equity = (1 + rets).cumprod()
    n_trades = int(sum(int((sig.diff().abs() > 0).sum()) for sig in signals.values()))
    return {
        "algorithm": algorithm,
        "symbols": list(features.keys()),
        "period": period,
        "sharpe": round(float(compute_sharpe_ratio(rets)), 3),
        "total_return_pct": round(float((equity.iloc[-1] - 1) * 100), 2),
        "annualized_return_pct": round(float(compute_annualized_return(equity) * 100), 2),
        "max_drawdown_pct": round(float(compute_max_drawdown(equity) * 100), 2),
        "n_trades": n_trades,
        "win_rate_pct": round(float(compute_win_rate(rets) * 100), 1),
        "params_used": params,
        "note": "single-asset vectorized backtest, no purged CV — indicative only",
    }


def search_memory(ctx: Any, query: str, limit: int = 5, min_robustness: float = 0.0) -> dict[str, Any]:
    try:
        from astra.memory.engine import MemoryEngine, MemoryQuery

        engine = MemoryEngine(ctx.db_factory())
        records = run_async(engine.retrieve(MemoryQuery(text=query, limit=limit, min_robustness=min_robustness)))
    except Exception as e:
        return {"insights": [], "note": f"no research memory available ({type(e).__name__})"}

    insights = [{
        "topic": r.topic,
        "claim": (r.claim or "")[:200],
        "robustness": round(float(r.robustness_score), 2),
        "support_count": r.support_count,
        "contradiction_count": r.contradiction_count,
        "tags": list(r.tags)[:6],
    } for r in records]
    return {"insights": insights, "note": "" if insights else "no prior validation memory"}


def build_strategy(ctx: Any, **spec_fields: Any) -> dict[str, Any]:
    valid = {f.name for f in dataclasses.fields(StrategySpec)}
    kwargs = {k: v for k, v in spec_fields.items() if k in valid}
    try:
        spec = StrategySpec(**kwargs)
    except Exception as e:
        return {"status": "error", "error": f"invalid spec: {e}"}

    if not spec.is_complete:
        return {"status": "incomplete", "missing_fields": spec.missing_fields}

    # Record build intent; the chat endpoint executes the existing _trigger_build flow.
    ctx.build_intent = spec
    return {
        "status": "build_queued",
        "spec_id": spec.spec_id,
        "summary": {
            "strategy_type": spec.strategy_type,
            "symbols": spec.symbols,
            "timeframe": spec.timeframe,
            "target_return": spec.target_return,
            "max_drawdown": spec.max_drawdown,
        },
    }


TOOL_REGISTRY = {
    "list_algorithms": list_algorithms,
    "get_market_data": get_market_data,
    "quick_backtest": quick_backtest,
    "search_memory": search_memory,
    "build_strategy": build_strategy,
}
