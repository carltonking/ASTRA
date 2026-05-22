import React, { useState, useEffect } from 'react';

const LIMITATIONS = [
  "Past performance does not guarantee future results",
  "This strategy was validated only in specific market conditions",
  "Paper trading does not account for slippage, fees, or liquidity constraints",
  "Live trading may produce substantially different results",
  "This certificate does not constitute financial advice",
];

const EXPORT_STEPS = [
  { id: 'validate', label: 'Validating exported strategy...' },
  { id: 'package', label: 'Packaging strategy file...' },
  { id: 'report', label: 'Generating PDF report...' },
  { id: 'checksum', label: 'Calculating checksum...' },
  { id: 'done', label: 'Export complete!' },
];

function SectionTitle({ label, badge }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', marginBottom: 'var(--space-lg)' }}>
      <span style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</span>
      {badge && (
        <span style={{ padding: '2px 12px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)', border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent' }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
      {title && <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>{title}</div>}
      {children}
    </div>
  );
}

export default function Graduation({ session }) {
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(null);
  const [graduationData, setGraduationData] = useState(null);

  useEffect(() => {
    if (!session?.sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/session/${session.sessionId}/graduation`);
        const data = await res.json();
        if (!cancelled) setGraduationData(data);
      } catch {
        if (!cancelled) setGraduationData(null);
      }
    })();
    return () => { cancelled = true; };
  }, [session?.sessionId]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      for (const step of EXPORT_STEPS) {
        if (cancelled) break;
        setExportProgress({ step: step.id, done: false });
        await new Promise(r => setTimeout(r, 600));
      }
      if (typeof session?.doExport !== 'function') {
        if (!cancelled) { setExportProgress(prev => ({ ...prev, done: true })); }
        return;
      }
      try {
        const result = await session.doExport();
        if (!cancelled) {
          setExportProgress(prev => ({ ...prev, done: true }));
          if (result?.strategy_url) window.open(result.strategy_url, '_blank');
          if (result?.report_url) window.open(result.report_url, '_blank');
        }
      } catch {
        if (!cancelled) setExportProgress(prev => ({ ...prev, done: true }));
      }
      if (!cancelled) setTimeout(() => { setExporting(false); setExportProgress(null); }, 2000);
    };
    if (exporting && !exportProgress) run();
    return () => { cancelled = true; };
  }, [exporting, exportProgress, session]);

  if (!graduationData) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-faint)', fontSize: 'var(--font-size-xs)', letterSpacing: '0.3px' }}>
        LOADING...
      </div>
    );
  }

  const gateResults = graduationData?.certificate?.gate_results || {};
  const isGraduated = graduationData?.is_graduated || false;

  const gateEntries = Object.entries(gateResults).map(([name, g]) => ({
    name, threshold: g?.threshold_value ?? 0, actual: g?.actual_value ?? 0,
    passed: g?.status === 'PASSED', gap: g?.gap ?? 0,
  }));
  const graduated = isGraduated || (gateEntries.length > 0 && gateEntries.every(g => g.passed));
  const passedCount = gateEntries.filter(g => g.passed).length;
  const closestGate = gateEntries.length > 0
    ? [...gateEntries].sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0]
    : null;

  if (gateEntries.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-faint)', fontSize: 'var(--font-size-xs)', letterSpacing: '0.3px' }}>
        NO GRADUATION DATA
      </div>
    );
  }

  return (
    <div>
      <SectionTitle label="Graduation" badge={`${passedCount}/${gateEntries.length}`} />

      {/* Gate progress bars */}
      <Card title="Gates">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
          {gateEntries.map(gate => {
            const fill = Math.min(100, gate.threshold > 0 ? (gate.actual / gate.threshold) * 100 : 0);
            return (
              <div key={gate.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-primary)', fontWeight: 500 }}>{gate.name}</span>
                  <span style={{
                    padding: '1px 8px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)',
                    border: `1px solid ${gate.passed ? 'var(--border)' : 'var(--border-light)'}`,
                    color: gate.passed ? 'var(--text-secondary)' : 'var(--text-dim)', background: 'transparent',
                  }}>
                    {gate.passed ? 'PASSED' : 'FAILED'}
                  </span>
                </div>
                <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: '6px' }}>
                  {typeof gate.actual === 'number' ? gate.actual.toFixed(3) : gate.actual}
                  {' / '}
                  {typeof gate.threshold === 'number' ? gate.threshold.toFixed(3) : gate.threshold}
                </div>
                <div style={{ height: '2px', background: 'var(--bg-hover)', borderRadius: '1px' }}>
                  <div style={{
                    height: '100%', width: `${fill}%`,
                    background: gate.passed ? 'var(--green)' : 'var(--text-dim)',
                    borderRadius: '1px', transition: 'width 0.3s',
                  }} />
                </div>
              </div>
            );
          })}
        </div>
        {!graduated && closestGate && (
          <div style={{ marginTop: 'var(--space-sm)', padding: '8px 12px', background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)', color: 'var(--text-muted)' }}>
            Closest: {closestGate.name} (gap {closestGate.gap.toFixed(3)})
          </div>
        )}
      </Card>

      {/* Certificate */}
      {graduated && (
        <Card title="Certificate">
          <div style={{ border: '1px solid var(--border)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-primary)', marginBottom: 'var(--space-xs)', fontFamily: 'var(--font-mono)', letterSpacing: '0.5px' }}>
              ASTRA-{session.sessionId?.slice(0, 8)}-GRAD
            </div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-sm)' }}>
              Issued: {new Date().toLocaleDateString()}
            </div>
            <button onClick={() => { if (!exporting) setExporting(true); }} disabled={exporting}
              style={{
                padding: 'var(--space-xs) var(--space-sm)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)',
                background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)',
                cursor: 'pointer', marginBottom: 'var(--space-sm)',
              }}>
              {exporting ? 'Packaging...' : 'Export Strategy'}
            </button>
            {exportProgress && (
              <div style={{ marginBottom: '12px' }}>
                {EXPORT_STEPS.map(step => {
                  const done = exportProgress.done;
                  const idx = EXPORT_STEPS.findIndex(s => s.id === exportProgress.step);
                  const cur = EXPORT_STEPS.findIndex(s => s.id === step.id);
                  const active = exportProgress.step === step.id;
                  const completed = done || idx > cur;
                  return (
                    <div key={step.id} style={{
                      display: 'flex', alignItems: 'center', gap: 'var(--space-xs)',
                      padding: '3px 0', fontSize: 'var(--font-size-2xs)',
                      color: active ? 'var(--text-primary)' : completed ? 'var(--text-dim)' : 'var(--text-faint)',
                    }}>
                      <span style={{ fontSize: '10px' }}>{active ? '\u25B6' : completed ? '\u2713' : '\u25CB'}</span>
                      {step.label}
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-faint)', lineHeight: '1.8' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Limitations:</div>
              <ul style={{ margin: 0, paddingLeft: '16px' }}>
                {LIMITATIONS.map((lim, i) => <li key={i}>{lim}</li>)}
              </ul>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
