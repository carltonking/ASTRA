import React from 'react';

const STEPS = ['Planning', 'Building', 'Data Download', 'Leakage Check', 'Backtest', 'Review Board', 'Paper Deploy', 'Monitoring'];

const STATUS_BADGE = {
  PLANNING: { label: 'Planning', color: '#777' },
  BUILDING: { label: 'Building', color: '#888' },
  RUNNING: { label: 'Running', color: '#999' },
  OPTIMIZING: { label: 'Optimizing', color: '#777' },
  PAPER_TRADING: { label: 'Paper Trading', color: '#22c55e' },
  GRADUATED: { label: 'Graduated', color: '#22c55e' },
  FAILED: { label: 'Failed', color: '#ef5350' },
};

function SectionTitle({ label, badge }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
      <span style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8' }}>{label}</span>
      {badge && (
        <span style={{
          padding: '2px 12px', borderRadius: '9999px',
          fontSize: '11px', border: '1px solid #333',
          color: '#aaa', background: 'transparent',
        }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function DotStepper({ steps, current }) {
  return (
    <div style={{ marginBottom: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, position: 'relative' }}>
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: i <= current ? '#e8e8e8' : '#1e1e1e',
              marginBottom: '6px', transition: 'background 0.3s',
              position: 'relative', zIndex: 1,
            }} />
            <span style={{
              fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.4px',
              color: i === current ? '#e8e8e8' : i < current ? '#888' : '#444',
              fontWeight: i === current ? 600 : 400,
              textAlign: 'center', whiteSpace: 'nowrap',
            }}>
              {s}
            </span>
          </div>
        ))}
      </div>
      <div style={{ height: '1px', background: '#1e1e1e', marginTop: '-4px', position: 'relative' }}>
        <div style={{
          height: '100%', width: `${((current + 1) / steps.length) * 100}%`,
          background: '#555', transition: 'width 0.4s',
        }} />
      </div>
    </div>
  );
}

function InfoCard({ title, children }) {
  return (
    <div style={{ background: '#161616', border: '1px solid #1e1e1e', borderRadius: '8px', padding: '20px', marginBottom: '20px' }}>
      <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8', marginBottom: '16px' }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: '1px solid #1a1a1a', fontSize: '13px',
    }}>
      <span style={{ color: '#555' }}>{label}</span>
      <span style={{ color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace", fontSize: '13px' }}>
        {value}
      </span>
    </div>
  );
}

export default function Overview({ session }) {
  const state = session.sessionState || {};
  const status = state.status || 'PLANNING';
  const badge = STATUS_BADGE[status] || { label: status, color: '#888' };

  const stepIdx = { PLANNING: 0, BUILDING: 1, RUNNING: 2, OPTIMIZING: 4, PAPER_TRADING: 5, GRADUATED: 7 };
  const currentStep = stepIdx[status] ?? 0;

  return (
    <div>
      <SectionTitle label="Overview" badge={badge.label} />

      <DotStepper steps={STEPS} current={currentStep} />

      <InfoCard title="Session Info">
        <Row label="Session ID" value={session.sessionId ? session.sessionId.slice(0, 8) + '\u2026' : '\u2014'} />
        <Row label="Status" value={badge.label} />
        <Row label="Strategy Type" value={state.spec?.strategy_type || '\u2014'} />
        <Row label="Symbols" value={state.spec?.symbols?.join(', ') || '\u2014'} />
      </InfoCard>

      {session.sessionId && (
        <button onClick={session.fetchState}
          style={{
            padding: '8px 16px', borderRadius: '6px', border: '1px solid #2e2e2e',
            background: 'transparent', color: '#aaa', fontSize: '13px',
            cursor: 'pointer',
          }}>
          Refresh State
        </button>
      )}
    </div>
  );
}
