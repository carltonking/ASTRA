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
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
      <span style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8' }}>{label}</span>
      {badge && (
        <span style={{ padding: '2px 12px', borderRadius: '9999px', fontSize: '11px', border: '1px solid #333', color: '#aaa', background: 'transparent' }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div style={{ background: '#161616', border: '1px solid #1e1e1e', borderRadius: '8px', padding: '20px', marginBottom: '20px' }}>
      {title && <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8', marginBottom: '16px' }}>{title}</div>}
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

  if (!graduationData) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: '#444', fontSize: '12px', letterSpacing: '0.3px' }}>
        LOADING...
      </div>
    );
  }

  const gateResults = graduationData.certificate?.gate_results || {};
  const progress = graduationData.progress || [];
  const isGraduated = graduationData.is_graduated || false;

  const gateEntries = Object.entries(gateResults).map(([name, g]) => ({
    name, threshold: g.threshold_value ?? 0, actual: g.actual_value ?? 0,
    passed: g.status === 'PASSED', gap: g.gap ?? 0,
  }));
  const graduated = isGraduated || (gateEntries.length > 0 && gateEntries.every(g => g.passed));
  const passedCount = gateEntries.filter(g => g.passed).length;
  const closestGate = [...gateEntries].sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0];

  useEffect(() => {
    let cancelled = false;
    if (exporting && !exportProgress) {
      (async () => {
        for (const step of EXPORT_STEPS) {
          if (cancelled) break;
          setExportProgress({ step: step.id, done: false });
          await new Promise(r => setTimeout(r, 600));
        }
        const result = await session.doExport();
        if (!cancelled) {
          setExportProgress(prev => ({ ...prev, done: true }));
          if (result?.strategy_url) window.open(result.strategy_url, '_blank');
          if (result?.report_url) window.open(result.report_url, '_blank');
        }
        if (!cancelled) setTimeout(() => { setExporting(false); setExportProgress(null); }, 2000);
      })();
    }
    return () => { cancelled = true; };
  }, [exporting]);

  if (gateEntries.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: '#444', fontSize: '12px', letterSpacing: '0.3px' }}>
        NO GRADUATION DATA
      </div>
    );
  }

  return (
    <div>
      <SectionTitle label="Graduation" badge={`${passedCount}/${gateEntries.length}`} />

      {/* Gate progress bars */}
      <Card title="Gates">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {gateEntries.map(gate => {
            const fill = Math.min(100, gate.threshold > 0 ? (gate.actual / gate.threshold) * 100 : 0);
            return (
              <div key={gate.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontSize: '12px', color: '#e8e8e8', fontWeight: 500 }}>{gate.name}</span>
                  <span style={{
                    padding: '1px 8px', borderRadius: '9999px', fontSize: '10px',
                    border: `1px solid ${gate.passed ? '#333' : '#444'}`,
                    color: gate.passed ? '#aaa' : '#666', background: 'transparent',
                  }}>
                    {gate.passed ? 'PASSED' : 'FAILED'}
                  </span>
                </div>
                <div style={{ fontSize: '11px', color: '#555', marginBottom: '6px' }}>
                  {typeof gate.actual === 'number' ? gate.actual.toFixed(3) : gate.actual}
                  {' / '}
                  {typeof gate.threshold === 'number' ? gate.threshold.toFixed(3) : gate.threshold}
                </div>
                <div style={{ height: '2px', background: '#1e1e1e', borderRadius: '1px' }}>
                  <div style={{
                    height: '100%', width: `${fill}%`,
                    background: gate.passed ? '#22c55e' : '#555',
                    borderRadius: '1px', transition: 'width 0.3s',
                  }} />
                </div>
              </div>
            );
          })}
        </div>
        {!graduated && closestGate && (
          <div style={{ marginTop: '16px', padding: '8px 12px', background: '#1e1e1e', borderRadius: '4px', fontSize: '11px', color: '#888' }}>
            Closest: {closestGate.name} (gap {closestGate.gap.toFixed(3)})
          </div>
        )}
      </Card>

      {/* Certificate */}
      {graduated && (
        <Card title="Certificate">
          <div style={{ border: '1px solid #1e1e1e', padding: '20px', borderRadius: '6px', background: '#111' }}>
            <div style={{ fontSize: '12px', color: '#e8e8e8', marginBottom: '8px', fontFamily: "'JetBrains Mono', 'Fira Code', monospace", letterSpacing: '0.5px' }}>
              ASTRA-{session.sessionId?.slice(0, 8)}-GRAD
            </div>
            <div style={{ fontSize: '11px', color: '#555', marginBottom: '16px' }}>
              Issued: {new Date().toLocaleDateString()}
            </div>
            <button onClick={() => { if (!exporting) setExporting(true); }} disabled={exporting}
              style={{
                padding: '8px 16px', borderRadius: '6px', border: '1px solid #2e2e2e',
                background: 'transparent', color: '#aaa', fontSize: '13px',
                cursor: 'pointer', marginBottom: '12px',
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
                      display: 'flex', alignItems: 'center', gap: '8px',
                      padding: '3px 0', fontSize: '11px',
                      color: active ? '#e8e8e8' : completed ? '#666' : '#333',
                    }}>
                      <span style={{ fontSize: '10px' }}>{active ? '\u25B6' : completed ? '\u2713' : '\u25CB'}</span>
                      {step.label}
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ fontSize: '10px', color: '#444', lineHeight: '1.8' }}>
              <div style={{ fontWeight: 500, color: '#666', marginBottom: '4px' }}>Limitations:</div>
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
