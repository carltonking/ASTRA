import React, { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function SectionTitle({ label }) {
  return <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-lg)' }}>{label}</div>;
}

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

export default function Optimization({ session }) {
  const state = session.sessionState || {};
  const history = state.optimizationHistory || [];
  const specSymbols = state.spec?.symbols || [];
  const [symbolsInput, setSymbolsInput] = useState(specSymbols.join(', ') || 'AAPL');

  const cycles = history.length > 0
    ? history.map((entry, i) => ({
        cycle: i + 1,
        sharpe: entry.sharpe || entry.mean_sharpe || 0,
        dsr: entry.dsr || entry.deflated_sharpe || 0,
        action: entry.action || entry.status || '\u2014',
        paramsChanged: entry.params_changed || entry.summary || '\u2014',
      }))
    : null;

  if (!cycles || cycles.length === 0) {
    return (
      <div>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-faint)', fontSize: 'var(--font-size-xs)', letterSpacing: '0.3px' }}>
          NO OPTIMIZATION DATA
        </div>
        <ParameterPresets sessionId={session.session_id} />
      </div>
    );
  }

  const chartData = cycles.map(c => ({ cycle: c.cycle, sharpe: c.sharpe, dsr: c.dsr }));
  const cycling = cycles.some(c =>
    c.action?.toLowerCase().includes('abandon') || c.action?.toLowerCase().includes('cycle')
  );

  return (
    <div>
      <SectionTitle label="Optimization" />

      <Card title="Symbols">
        <div style={{ display: 'flex', gap: 'var(--space-xs)', alignItems: 'center' }}>
          <input value={symbolsInput} onChange={e => setSymbolsInput(e.target.value)}
            placeholder="AAPL, MSFT, GOOGL"
            style={{ flex: 1, padding: 'var(--space-xs) var(--space-sm)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)', fontFamily: 'var(--font-mono)' }} />
          <span style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>Comma-separated tickers</span>
        </div>
        {specSymbols.length > 1 && (
          <div style={{ marginTop: 'var(--space-xs)', fontSize: 'var(--font-size-2xs)', color: 'var(--green)' }}>
            Multi-symbol optimization ({specSymbols.length} symbols)
          </div>
        )}
      </Card>

      <Card title="Sharpe & DSR by Cycle">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
            <XAxis dataKey="cycle" stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
            <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
            <Legend wrapperStyle={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-muted)' }} />
            <Line type="monotone" dataKey="sharpe" stroke="var(--text-muted)" strokeWidth={1} dot={{ r: 3, fill: 'var(--text-muted)' }} />
            <Line type="monotone" dataKey="dsr" stroke="var(--text-secondary)" strokeWidth={1} dot={{ r: 3, fill: 'var(--text-secondary)' }} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Cycle History">
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>
          <span style={{ minWidth: '24px' }}>#</span>
          <span style={{ minWidth: '70px' }}>Sharpe</span>
          <span style={{ minWidth: '70px' }}>DSR</span>
          <span style={{ minWidth: '80px' }}>Action</span>
          <span style={{ flex: 1, textAlign: 'right' }}>Details</span>
        </div>
        {cycles.map(c => (
          <Row key={c.cycle} label={String(c.cycle)}
            value={`${c.sharpe.toFixed(3)}  ${c.dsr.toFixed(3)}  ${c.action}  ${c.paramsChanged}`}
            mono />
        ))}
          {cycling && (
            <div style={{
              marginTop: 'var(--space-sm)', padding: '8px 12px',
              background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--font-size-2xs)', color: 'var(--yellow)',
              border: '1px solid var(--border)',
            }}>
              ⚠ Cycling detected — optimization will be abandoned
            </div>
          )}
        </Card>
        <ParameterPresets sessionId={session.session_id} />
      </div>
    );
  }

function ParameterPresets({ sessionId }) {
  const [presets, setPresets] = useState([]);
  const [name, setName] = useState('');
  const [params, setParams] = useState('{}');
  const [strategyType, setStrategyType] = useState('momentum');

  const loadPresets = useCallback(() => {
    if (!sessionId) return;
    fetch(`/api/session/${sessionId}/presets`)
      .then(r => r.json())
      .then(d => setPresets(d))
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => { loadPresets(); }, [loadPresets]);

  const savePreset = async () => {
    try {
      const p = JSON.parse(params);
      const res = await fetch(`/api/session/${sessionId}/presets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, strategy_type: strategyType, params: p }),
      });
      if (res.ok) {
        setName('');
        setParams('{}');
        loadPresets();
      }
    } catch (e) { alert('Invalid JSON: ' + e.message); }
  };

  const deletePreset = async (presetId) => {
    const res = await fetch(`/api/session/${sessionId}/presets/${presetId}`, { method: 'DELETE' });
    if (res.ok) loadPresets();
  };

  const tbodyStyle = { borderBottom: '1px solid var(--border)' };
  const tdStyle = { padding: '8px 12px', fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' };

  return (
    <Card title="Parameter Presets">
      <div style={{ display: 'flex', gap: 'var(--space-xs)', marginBottom: 'var(--space-sm)', alignItems: 'center' }}>
        <input placeholder="Preset name" value={name} onChange={e => setName(e.target.value)}
          style={{ flex: 1, padding: '6px 10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-xs)' }} />
        <select value={strategyType} onChange={e => setStrategyType(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 'var(--font-size-xs)' }}>
          <option value="momentum">Momentum</option>
          <option value="mean_reversion">Mean Reversion</option>
          <option value="breakout">Breakout</option>
          <option value="pairs">Pairs</option>
          <option value="dca">DCA</option>
        </select>
        <button onClick={savePreset} disabled={!name || !params}
          style={{ padding: '6px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'transparent', color: name ? 'var(--text-secondary)' : 'var(--text-faint)', fontSize: 'var(--font-size-xs)', cursor: name ? 'pointer' : 'default' }}>
          Save
        </button>
      </div>
      <div style={{ position: 'relative' }}>
        <textarea value={params} onChange={e => setParams(e.target.value)}
          placeholder='{"fast_ma": 20, "slow_ma": 50, "rsi_threshold": 30}'
          style={{ width: '100%', padding: 'var(--space-xs)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-2xs)', fontFamily: 'var(--font-mono)', minHeight: '60px', resize: 'vertical', outline: 'none' }} />
      </div>
      {presets.length > 0 && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ display: 'flex', padding: '6px 12px', fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', borderBottom: '1px solid var(--border)' }}>
            <span style={{ flex: 1 }}>Name</span>
            <span style={{ width: '100px' }}>Type</span>
            <span style={{ width: '20px' }}></span>
          </div>
          {presets.map(p => (
            <div key={p.preset_id} style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ flex: 1, color: 'var(--text-primary)', fontSize: 'var(--font-size-xs)' }}>{p.name}</span>
              <span style={{ width: '100px', color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)' }}>{p.strategy_type}</span>
              <button onClick={() => deletePreset(p.preset_id)}
                style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '14px', padding: '2px' }} title="Delete">
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {presets.length === 0 && (
        <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)', fontStyle: 'italic' }}>
          No saved presets
        </div>
      )}
    </Card>
  );
}
