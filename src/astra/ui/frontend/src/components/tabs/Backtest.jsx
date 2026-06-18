import React, { useEffect, useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, ComposedChart } from 'recharts';
import useWebSocket from '../../hooks/useWebSocket';
import useAlpaca from '../../hooks/useAlpaca';

function SectionTitle({ label }) {
  return <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-lg)' }}>{label}</div>;
}

const PERIODS = ['1D', '1M', '1Y', 'all'];

// Live paper-trading performance. Charts show REAL equity from the Alpaca paper
// account (current market), not a historical backtest simulation. The pre-deploy
// validation stats (CPCV) are kept only as small reference cards.
export default function Backtest({ session }) {
  const { lastEvents } = useWebSocket(session?.sessionId);
  const { configured, account, portfolioHistory, fetchPortfolioHistory } = useAlpaca();
  const [period, setPeriod] = useState('1M');
  const [validation, setValidation] = useState(null);

  // Poll live portfolio history on mount + period change + every 30s.
  useEffect(() => {
    if (!configured) return;
    const tf = period === '1D' ? '5Min' : '1D';
    fetchPortfolioHistory(period, tf);
    const id = setInterval(() => fetchPortfolioHistory(period, tf), 30000);
    return () => clearInterval(id);
  }, [configured, period, fetchPortfolioHistory]);

  // Validation stats from the pipeline (reference only — not plotted).
  useEffect(() => {
    const event = lastEvents.find(ev => ev.event === 'pipeline.backtest_complete');
    if (event?.data) {
      const cpcv = event.data.cpcv_summary || {};
      setValidation({
        meanSharpe: cpcv.mean_sharpe ?? 0,
        dsr: cpcv.dsr ?? 0,
        overfitProb: cpcv.overfitting_probability ?? 0,
        leakageVerdict: event.data.leakage_verdict || 'PENDING',
        reviewVerdict: event.data.review_board_status || 'PENDING',
      });
    }
  }, [lastEvents]);

  // Build live equity + drawdown series from real Alpaca portfolio history.
  const { equitySeries, drawdownSeries, liveStats } = useMemo(() => {
    const ts = portfolioHistory?.timestamp || [];
    const eq = portfolioHistory?.equity || [];
    if (!eq.length) return { equitySeries: [], drawdownSeries: [], liveStats: null };
    let peak = -Infinity;
    const equitySeries = [];
    const drawdownSeries = [];
    eq.forEach((v, i) => {
      if (v == null) return;
      const t = ts[i] ? new Date(ts[i] * 1000) : null;
      const label = t
        ? (period === '1D'
            ? t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : t.toLocaleDateString([], { month: 'short', day: 'numeric' }))
        : String(i);
      equitySeries.push({ label, equity: v });
      peak = Math.max(peak, v);
      drawdownSeries.push({ label, dd: peak > 0 ? ((v - peak) / peak) * 100 : 0 });
    });
    const first = equitySeries[0]?.equity ?? 0;
    const last = equitySeries[equitySeries.length - 1]?.equity ?? 0;
    const maxDd = Math.min(0, ...drawdownSeries.map(d => d.dd));
    return {
      equitySeries,
      drawdownSeries,
      liveStats: {
        totalReturn: first ? ((last - first) / first) * 100 : 0,
        maxDrawdown: maxDd,
        current: last,
      },
    };
  }, [portfolioHistory, period]);

  const card = { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' };
  const hasLive = equitySeries.length > 0;

  return (
    <div>
      <SectionTitle label="Live Paper Trading" />

      {!configured && (
        <div style={{ ...card, color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)' }}>
          Broker not configured — set Alpaca paper credentials to stream live performance.
        </div>
      )}

      {/* Period switcher */}
      <div style={{ display: 'flex', gap: 'var(--space-xs)', marginBottom: 'var(--space-md)' }}>
        {PERIODS.map(p => (
          <button key={p} onClick={() => setPeriod(p)} style={{
            padding: '4px 14px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)',
            fontWeight: 500, cursor: 'pointer',
            border: '1px solid var(--border)',
            background: period === p ? 'var(--bg-hover)' : 'transparent',
            color: period === p ? 'var(--text-primary)' : 'var(--text-dim)',
          }}>{p.toUpperCase()}</button>
        ))}
      </div>

      {/* Live equity curve */}
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--space-sm)' }}>
          <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>Equity (live · Alpaca paper)</span>
          {account?.equity != null && (
            <span style={{ fontSize: 'var(--font-size-md)', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              ${Number(account.equity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          )}
        </div>
        {hasLive ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={equitySeries}>
              <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
              <XAxis dataKey="label" stroke="var(--text-faint)" tick={{ fontSize: 10 }} minTickGap={32} />
              <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
              <Line type="monotone" dataKey="equity" stroke="var(--green, #4ade80)" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)' }}>
            {configured ? 'AWAITING LIVE DATA — deploy a strategy to begin trading' : 'NO BROKER'}
          </div>
        )}
      </div>

      {/* Live drawdown */}
      <div style={card}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Drawdown (live)</div>
        {hasLive ? (
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={drawdownSeries}>
              <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
              <XAxis dataKey="label" stroke="var(--text-faint)" tick={{ fontSize: 10 }} minTickGap={32} />
              <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
              <Area type="monotone" dataKey="dd" fill="#2a1a1a" stroke="var(--red)" strokeWidth={1} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)' }}>No live drawdown yet</div>
        )}
      </div>

      {/* Live performance metrics */}
      {liveStats && (
        <div style={card}>
          <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Live Performance</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-sm)' }}>
            {[
              ['Return (period)', `${liveStats.totalReturn.toFixed(2)}%`],
              ['Max Drawdown', `${liveStats.maxDrawdown.toFixed(2)}%`],
              ['Current Equity', `$${liveStats.current.toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
            ].map(([k, v]) => (
              <div key={k} style={{ background: 'var(--bg-surface)', padding: 'var(--space-sm)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--text-dim)' }}>
                <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)', fontWeight: 500 }}>{k}</div>
                <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pre-deploy validation — reference only, NOT performance */}
      {validation && (
        <div style={card}>
          <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-2xs)' }}>Validation (pre-deploy)</div>
          <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-sm)' }}>
            Robustness checks run before deployment. Not live performance.
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--space-sm)', marginBottom: 'var(--space-sm)' }}>
            {[
              ['Mean Sharpe (CPCV)', validation.meanSharpe?.toFixed(3)],
              ['Deflated Sharpe (DSR)', validation.dsr?.toFixed(3)],
              ['Overfit Probability', validation.overfitProb != null ? `${(validation.overfitProb * 100).toFixed(1)}%` : '—'],
            ].map(([k, v]) => (
              <div key={k} style={{ background: 'var(--bg-surface)', padding: 'var(--space-sm)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--text-faint)' }}>
                <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)', fontWeight: 500 }}>{k}</div>
                <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <Pill label={`Leakage: ${validation.leakageVerdict}`} />
            <Pill label={`Review: ${validation.reviewVerdict}`} />
          </div>
        </div>
      )}
    </div>
  );
}

function Pill({ label }) {
  return (
    <span style={{
      padding: '3px 12px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)', fontWeight: 500,
      border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent',
    }}>
      {label}
    </span>
  );
}
