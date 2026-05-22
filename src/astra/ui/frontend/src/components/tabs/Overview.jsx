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
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-lg)' }}>
      <span style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</span>
      {badge && (
        <span style={{
          padding: '2px 12px', borderRadius: 'var(--radius-full)',
          fontSize: 'var(--font-size-2xs)', border: '1px solid var(--border)',
          color: 'var(--text-secondary)', background: 'transparent',
        }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function DotStepper({ steps, current }) {
  return (
    <div style={{ marginBottom: 'var(--space-lg)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-xs)' }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, position: 'relative' }}>
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: i <= current ? 'var(--text-primary)' : 'var(--bg-hover)',
              marginBottom: '6px', transition: 'background 0.3s',
              position: 'relative', zIndex: 1,
            }} />
            <span style={{
              fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.4px',
              color: i === current ? 'var(--text-primary)' : i < current ? 'var(--text-muted)' : 'var(--text-faint)',
              fontWeight: i === current ? 600 : 400,
              textAlign: 'center', whiteSpace: 'nowrap',
            }}>
              {s}
            </span>
          </div>
        ))}
      </div>
      <div style={{ height: '1px', background: 'var(--bg-hover)', marginTop: '-4px', position: 'relative' }}>
        <div style={{
          height: '100%', width: `${((current + 1) / steps.length) * 100}%`,
          background: 'var(--text-dim)', transition: 'width 0.4s',
        }} />
      </div>
    </div>
  );
}

function InfoCard({ title, children }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
      <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--font-size-sm)',
    }}>
      <span style={{ color: 'var(--text-dim)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-sm)' }}>
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
            padding: 'var(--space-xs) var(--space-sm)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)',
            background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)',
            cursor: 'pointer',
          }}>
          Refresh State
        </button>
      )}
    </div>
  );
}
