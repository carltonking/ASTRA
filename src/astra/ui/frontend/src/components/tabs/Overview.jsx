import React from 'react';

const STEPS = [
  'Planning', 'Building', 'Data Download', 'Leakage Check',
  'Backtest', 'Review Board', 'Paper Deploy', 'Monitoring',
];

const STATUS_BADGE = {
  PLANNING: { label: 'Planning', color: '#f0a030' },
  BUILDING: { label: 'Building', color: '#3090f0' },
  RUNNING: { label: 'Running', color: '#30c0f0' },
  OPTIMIZING: { label: 'Optimizing', color: '#9030f0' },
  PAPER_TRADING: { label: 'Paper Trading', color: '#30f030' },
  GRADUATED: { label: 'Graduated', color: '#00c080' },
  FAILED: { label: 'Failed', color: '#f03030' },
};

export default function Overview({ session }) {
  const state = session.sessionState || {};
  const status = state.status || 'PLANNING';
  const badge = STATUS_BADGE[status] || { label: status, color: '#888' };

  const stepIndex = {
    PLANNING: 0, BUILDING: 1, RUNNING: 2,
    OPTIMIZING: 4, PAPER_TRADING: 6, GRADUATED: 7,
  };

  const currentStep = stepIndex[status] ?? 0;

  return (
    <div>
      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#e0e0e0' }}>
        Overview
        <span style={{
          marginLeft: '12px', padding: '3px 10px', borderRadius: '12px',
          fontSize: '12px', fontWeight: 600, background: badge.color + '22',
          color: badge.color, border: `1px solid ${badge.color}`,
        }}>
          {badge.label}
        </span>
      </h2>

      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
          {STEPS.map((step, i) => (
            <div key={i} style={{
              fontSize: '10px', textAlign: 'center', color: i <= currentStep ? '#3a6ea5' : '#555',
              fontWeight: i === currentStep ? 700 : 400, flex: 1,
            }}>
              {step}
            </div>
          ))}
        </div>
        <div style={{ height: '4px', background: '#333', borderRadius: '2px', position: 'relative' }}>
          <div style={{
            height: '100%', width: `${((currentStep + 1) / STEPS.length) * 100}%`,
            background: '#3a6ea5', borderRadius: '2px', transition: 'width 0.5s',
          }} />
        </div>
      </div>

      <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px', border: '1px solid #333' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: '#c0c0e0' }}>
          Session Info
        </h3>
        <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
          <tbody>
            {[
              ['Session ID', session.sessionId ? session.sessionId.slice(0, 8) + '...' : '-'],
              ['Status', badge.label],
              ['Strategy Type', state.spec?.strategy_type || '-'],
              ['Symbols', state.spec?.symbols?.join(', ') || '-'],
            ].map(([k, v]) => (
              <tr key={k} style={{ borderBottom: '1px solid #2a2a4a' }}>
                <td style={{ padding: '6px 8px', color: '#888' }}>{k}</td>
                <td style={{ padding: '6px 8px', color: '#c0c0e0' }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {session.sessionId && (
        <button onClick={session.fetchState}
          style={{ marginTop: '12px', padding: '6px 16px', background: '#2a2a4a',
                   border: '1px solid #444', borderRadius: '6px', color: '#c0c0e0',
                   cursor: 'pointer', fontSize: '12px' }}>
          Refresh State
        </button>
      )}
    </div>
  );
}
