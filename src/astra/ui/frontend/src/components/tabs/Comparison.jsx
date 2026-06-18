import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const fields = [
  { key: 'sharpe', label: 'Sharpe', mult: 1, fmt: v => v.toFixed(2) },
  { key: 'dsr', label: 'DSR', mult: 1, fmt: v => v.toFixed(2) },
  { key: 'annReturn', label: 'Ann. Return %', mult: 100, fmt: v => (v * 100).toFixed(1) },
  { key: 'maxDD', label: 'Max DD %', mult: 100, fmt: v => (v * 100).toFixed(1) },
  { key: 'winRate', label: 'Win Rate %', mult: 100, fmt: v => (v * 100).toFixed(1) },
  { key: 'nTrades', label: 'Trades', mult: 1, fmt: v => Math.round(v) },
];

function Card({ title, children }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
      {title && <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>{title}</div>}
      {children}
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--font-size-sm)',
    }}>
      <span style={{ color: 'var(--text-dim)' }}>{label}</span>
      <span style={{
        color: 'var(--text-primary)', textAlign: 'right',
        fontFamily: mono ? 'var(--font-mono)' : undefined,
      }}>
        {value}
      </span>
    </div>
  );
}

export default function Comparison({ session }) {
  const state = session?.sessionState || {};
  const history = state.optimizationHistory || [];

  const strategies = history.length > 0
    ? history.map((c, i) => ({
        name: `Cycle ${c.cycle || i + 1}`,
        sharpe: c.sharpe || 0,
        dsr: c.dsr || 0,
        annReturn: c.annualized_return || 0,
        maxDD: c.max_drawdown || 0,
        winRate: c.win_rate || 0,
        nTrades: c.n_trades || 0,
      }))
    : [];

  const chartData = fields.map(f => ({
    metric: f.label,
    ...Object.fromEntries(strategies.map(s => [s.name, f.mult * (s[f.key] || 0)])),
  }));

  const colors = ['#6366f1', '#22c55e', '#eab308', '#ef4444', '#3b82f6', '#a855f7', '#ec4899'];

  if (strategies.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-faint)', fontSize: 'var(--font-size-sm)' }}>
        No optimization history yet — run backtests to see comparisons here.
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-lg)' }}>Strategy Comparison</div>

      <Card title="Metrics Across Optimization Cycles">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} barGap={4}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
            <XAxis dataKey="metric" stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
            <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
            <Legend wrapperStyle={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-muted)' }} />
            {strategies.map((s, i) => (
              <Bar key={s.name} dataKey={s.name} fill={colors[i % colors.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Per-Cycle Breakdown">
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Cycle</th>
                {fields.map(f => <th key={f.key}>{f.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{s.name}</td>
                  {fields.map(f => <td key={f.key}>{f.fmt(s[f.key] || 0)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Best Performing">
        <Row label="Highest Sharpe" value={strategies.reduce((b, s) => s.sharpe > (b?.sharpe || -Infinity) ? s : b, strategies[0]).name} />
        <Row label="Highest DSR" value={strategies.reduce((b, s) => s.dsr > (b?.dsr || -Infinity) ? s : b, strategies[0]).name} />
        <Row label="Best Return" value={strategies.reduce((b, s) => s.annReturn > (b?.annReturn || -Infinity) ? s : b, strategies[0]).name} />
        <Row label="Lowest Drawdown" value={strategies.reduce((b, s) => s.maxDD < (b?.maxDD || Infinity) ? s : b, strategies[0]).name} />
      </Card>
    </div>
  );
}
