import React, { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

function SectionTitle({ label }) {
  return <div style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8', marginBottom: '24px' }}>{label}</div>;
}

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
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#444', fontSize: '12px', letterSpacing: '0.3px' }}>
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
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input value={symbolsInput} onChange={e => setSymbolsInput(e.target.value)}
            placeholder="AAPL, MSFT, GOOGL"
            style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '13px', fontFamily: 'monospace' }} />
          <span style={{ fontSize: '10px', color: '#555' }}>Comma-separated tickers</span>
        </div>
        {specSymbols.length > 1 && (
          <div style={{ marginTop: '8px', fontSize: '11px', color: '#22c55e' }}>
            Multi-symbol optimization ({specSymbols.length} symbols)
          </div>
        )}
      </Card>

      <Card title="Sharpe & DSR by Cycle">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="2 2" stroke="#1e1e1e" />
            <XAxis dataKey="cycle" stroke="#444" tick={{ fontSize: 10 }} />
            <YAxis stroke="#444" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: '4px', fontSize: '11px' }} />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#888' }} />
            <Line type="monotone" dataKey="sharpe" stroke="#888" strokeWidth={1} dot={{ r: 3, fill: '#888' }} />
            <Line type="monotone" dataKey="dsr" stroke="#aaa" strokeWidth={1} dot={{ r: 3, fill: '#aaa' }} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card title="Cycle History">
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #1e1e1e', fontSize: '11px', color: '#555' }}>
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
              marginTop: '12px', padding: '8px 12px',
              background: '#1e1e1e', borderRadius: '4px',
              fontSize: '11px', color: '#d0d030',
              border: '1px solid #2a2a1a',
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

  const tbodyStyle = { borderBottom: '1px solid #1a1a1a' };
  const tdStyle = { padding: '8px 12px', fontSize: '12px', color: '#888' };

  return (
    <Card title="Parameter Presets">
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
        <input placeholder="Preset name" value={name} onChange={e => setName(e.target.value)}
          style={{ flex: 1, padding: '6px 10px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '12px' }} />
        <select value={strategyType} onChange={e => setStrategyType(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#aaa', fontSize: '12px' }}>
          <option value="momentum">Momentum</option>
          <option value="mean_reversion">Mean Reversion</option>
          <option value="breakout">Breakout</option>
          <option value="pairs">Pairs</option>
          <option value="dca">DCA</option>
        </select>
        <button onClick={savePreset} disabled={!name || !params}
          style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #2e2e2e', background: 'transparent', color: name ? '#aaa' : '#333', fontSize: '12px', cursor: name ? 'pointer' : 'default' }}>
          Save
        </button>
      </div>
      <div style={{ position: 'relative' }}>
        <textarea value={params} onChange={e => setParams(e.target.value)}
          placeholder='{"fast_ma": 20, "slow_ma": 50, "rsi_threshold": 30}'
          style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '11px', fontFamily: 'monospace', minHeight: '60px', resize: 'vertical', outline: 'none' }} />
      </div>
      {presets.length > 0 && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ display: 'flex', padding: '6px 12px', fontSize: '10px', color: '#555', textTransform: 'uppercase', letterSpacing: '0.5px', borderBottom: '1px solid #1e1e1e' }}>
            <span style={{ flex: 1 }}>Name</span>
            <span style={{ width: '100px' }}>Type</span>
            <span style={{ width: '20px' }}></span>
          </div>
          {presets.map(p => (
            <div key={p.preset_id} style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #1a1a1a' }}>
              <span style={{ flex: 1, color: '#e8e8e8', fontSize: '12px' }}>{p.name}</span>
              <span style={{ width: '100px', color: '#555', fontSize: '11px' }}>{p.strategy_type}</span>
              <button onClick={() => deletePreset(p.preset_id)}
                style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: '14px', padding: '2px' }} title="Delete">
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {presets.length === 0 && (
        <div style={{ textAlign: 'center', padding: '20px', color: '#444', fontSize: '11px', fontStyle: 'italic' }}>
          No saved presets
        </div>
      )}
    </Card>
  );
}
