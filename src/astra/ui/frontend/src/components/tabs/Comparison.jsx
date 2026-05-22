import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

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
      <span style={{ color: 'var(--text-dim)', minWidth: '80px' }}>{label}</span>
      <span style={{
        color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)', textAlign: 'right',
        fontFamily: mono ? 'var(--font-mono)' : undefined,
      }}>
        {value}
      </span>
    </div>
  );
}

const INITIAL = [
  { name: 'Strategy A', sharpe: 0, dsr: 0, annReturn: 0, maxDD: 0, winRate: 0, nTrades: 0, label: 'A' },
  { name: 'Strategy B', sharpe: 0, dsr: 0, annReturn: 0, maxDD: 0, winRate: 0, nTrades: 0, label: 'B' },
];

export default function Comparison({ session }) {
  const [strategies, setStrategies] = useState(() => {
    try {
      const saved = localStorage.getItem('astra_comparison_data');
      return saved ? JSON.parse(saved) : INITIAL;
    } catch { return INITIAL; }
  });
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    localStorage.setItem('astra_comparison_data', JSON.stringify(strategies));
  }, [strategies]);

  const updateField = (idx, field, value) => {
    setStrategies(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: parseFloat(value) || 0 };
      return next;
    });
  };

  const addStrategy = () => {
    const nextLabel = String.fromCharCode(65 + strategies.length);
    setStrategies(prev => [...prev, { name: `Strategy ${nextLabel}`, sharpe: 0, dsr: 0, annReturn: 0, maxDD: 0, winRate: 0, nTrades: 0, label: nextLabel }]);
  };

  const removeStrategy = (idx) => {
    setStrategies(prev => prev.length > 2 ? prev.filter((_, i) => i !== idx) : prev);
  };

  const chartData = [
    { metric: 'Sharpe', ...Object.fromEntries(strategies.map((s, i) => [s.name, s.sharpe])) },
    { metric: 'DSR', ...Object.fromEntries(strategies.map((s, i) => [s.name, s.dsr])) },
    { metric: 'Ann. Return %', ...Object.fromEntries(strategies.map((s, i) => [s.name, s.annReturn * 100])) },
    { metric: 'Max DD %', ...Object.fromEntries(strategies.map((s, i) => [s.name, s.maxDD * 100])) },
    { metric: 'Win Rate %', ...Object.fromEntries(strategies.map((s, i) => [s.name, s.winRate * 100])) },
  ];

  const colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#a4de6c'];

  return (
    <div>
      <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-lg)' }}>Strategy Comparison</div>

      <Card title="Metrics Comparison">
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

      <Card title="Edit Strategies">
        {strategies.map((s, idx) => (
          <div key={idx} style={{
            display: 'flex', gap: 'var(--space-xs)', alignItems: 'center', flexWrap: 'wrap',
            padding: 'var(--space-xs) 0', borderBottom: '1px solid var(--border)',
          }}>
            <input value={s.name} onChange={e => {
              const next = [...strategies];
              next[idx] = { ...next[idx], name: e.target.value };
              setStrategies(next);
            }}
              style={{ width: '100px', padding: '4px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-xs)' }} />
            {['sharpe', 'dsr', 'annReturn', 'maxDD', 'winRate', 'nTrades'].map(field => (
              <div key={field} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
                <span style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', minWidth: '20px' }}>{field.replace(/^[a-z]/, c => c.toUpperCase())}</span>
                <input type="number" step="0.01" value={s[field]} onChange={e => updateField(idx, field, e.target.value)}
                  style={{ width: '60px', padding: '4px 6px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-2xs)' }} />
              </div>
            ))}
            {strategies.length > 2 && (
              <button onClick={() => removeStrategy(idx)}
                style={{ background: 'none', border: 'none', color: 'var(--red)', cursor: 'pointer', fontSize: '14px' }}>
                ✕
              </button>
            )}
          </div>
        ))}
        <button onClick={addStrategy}
          style={{ marginTop: 'var(--space-xs)', padding: '6px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-size-xs)', cursor: 'pointer' }}>
          + Add Strategy
        </button>
      </Card>

      <Card title="Best Performing">
        {strategies.length > 0 ? (
          <div>
            <Row label="Highest Sharpe" value={strategies.reduce((best, s) => s.sharpe > (best?.sharpe || -Infinity) ? s : best, strategies[0]).name} />
            <Row label="Highest DSR" value={strategies.reduce((best, s) => s.dsr > (best?.dsr || -Infinity) ? s : best, strategies[0]).name} />
            <Row label="Best Return" value={strategies.reduce((best, s) => s.annReturn > (best?.annReturn || -Infinity) ? s : best, strategies[0]).name} />
            <Row label="Lowest Drawdown" value={strategies.reduce((best, s) => s.maxDD < (best?.maxDD || Infinity) ? s : best, strategies[0]).name} />
          </div>
        ) : (
          <div style={{ color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)', textAlign: 'center', padding: 'var(--space-md)' }}>Add strategies to compare</div>
        )}
      </Card>
    </div>
  );
}
