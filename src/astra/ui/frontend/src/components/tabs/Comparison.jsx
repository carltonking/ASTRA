import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function Card({ title, children }) {
  return (
    <div style={{ background: '#161616', border: '1px solid #1e1e1e', borderRadius: '8px', padding: '20px', marginBottom: '20px' }}>
      {title && <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8', marginBottom: '16px' }}>{title}</div>}
      {children}
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: '1px solid #1a1a1a', fontSize: '13px',
    }}>
      <span style={{ color: '#555', minWidth: '80px' }}>{label}</span>
      <span style={{
        color: '#e8e8e8', fontSize: '13px', textAlign: 'right',
        fontFamily: mono ? "'JetBrains Mono', 'Fira Code', monospace" : undefined,
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
      <div style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8', marginBottom: '24px' }}>Strategy Comparison</div>

      <Card title="Metrics Comparison">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} barGap={4}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1e1e1e" />
            <XAxis dataKey="metric" stroke="#444" tick={{ fontSize: 10 }} />
            <YAxis stroke="#444" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: '4px', fontSize: '11px' }} />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#888' }} />
            {strategies.map((s, i) => (
              <Bar key={s.name} dataKey={s.name} fill={colors[i % colors.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Edit Strategies">
        {strategies.map((s, idx) => (
          <div key={idx} style={{
            display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap',
            padding: '8px 0', borderBottom: '1px solid #1a1a1a',
          }}>
            <input value={s.name} onChange={e => {
              const next = [...strategies];
              next[idx] = { ...next[idx], name: e.target.value };
              setStrategies(next);
            }}
              style={{ width: '100px', padding: '4px 8px', borderRadius: '4px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '12px' }} />
            {['sharpe', 'dsr', 'annReturn', 'maxDD', 'winRate', 'nTrades'].map(field => (
              <div key={field} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ fontSize: '10px', color: '#555', minWidth: '20px' }}>{field.replace(/^[a-z]/, c => c.toUpperCase())}</span>
                <input type="number" step="0.01" value={s[field]} onChange={e => updateField(idx, field, e.target.value)}
                  style={{ width: '60px', padding: '4px 6px', borderRadius: '4px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '11px' }} />
              </div>
            ))}
            {strategies.length > 2 && (
              <button onClick={() => removeStrategy(idx)}
                style={{ background: 'none', border: 'none', color: '#ef5350', cursor: 'pointer', fontSize: '14px' }}>
                ✕
              </button>
            )}
          </div>
        ))}
        <button onClick={addStrategy}
          style={{ marginTop: '8px', padding: '6px 14px', borderRadius: '6px', border: '1px solid #2e2e2e', background: 'transparent', color: '#aaa', fontSize: '12px', cursor: 'pointer' }}>
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
          <div style={{ color: '#444', fontSize: '11px', textAlign: 'center', padding: '20px' }}>Add strategies to compare</div>
        )}
      </Card>
    </div>
  );
}
