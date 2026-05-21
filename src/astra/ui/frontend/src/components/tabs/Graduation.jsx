import React, { useState, useEffect } from 'react';
import axios from 'axios';

const GATE_NAMES = [
  'dsr', 'annual_return', 'max_drawdown',
  'min_trades', 'max_degradation', 'min_calendar_days',
];

const GATE_LABELS = {
  dsr: 'Deflated Sharpe Ratio',
  annual_return: 'Annual Return',
  max_drawdown: 'Max Drawdown',
  min_trades: 'Min Trades',
  max_degradation: 'Degradation Score',
  min_calendar_days: 'Days Deployed',
};

export default function Graduation({ session }) {
  const [gradData, setGradData] = useState(null);
  const [exportResult, setExportResult] = useState(null);

  useEffect(() => {
    if (!session.sessionId) return;
    axios.get(`http://localhost:8000/api/session/${session.sessionId}/graduation`)
      .then(res => setGradData(res.data))
      .catch(() => {});
  }, [session.sessionId]);

  const handleExport = async () => {
    try {
      const res = await axios.post(`http://localhost:8000/api/session/${session.sessionId}/export`);
      setExportResult(res.data);
    } catch { /* ignore */ }
  };

  const cert = gradData?.certificate;
  const gates = cert?.gate_results || {};

  return (
    <div>
      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#e0e0e0' }}>
        Graduation
        {gradData?.is_graduated && (
          <span style={{
            marginLeft: '12px', padding: '3px 10px', borderRadius: '12px',
            fontSize: '12px', fontWeight: 600, background: '#1a3a1a',
            color: '#30d030', border: '1px solid #2a5a2a',
          }}>
            Graduated
          </span>
        )}
      </h2>

      {gradData?.progress?.length > 0 && (
        <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px',
                      border: '1px solid #333', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#c0c0e0' }}>
            Progress: {gradData.progress[gradData.progress.length - 1]?.gates_passed || 0} of 6 gates passed
          </h3>
          {GATE_NAMES.map(name => {
            const g = gates[name];
            if (!g) return null;
            const pct = g.threshold_value > 0
              ? Math.min(100, (g.actual_value / g.threshold_value) * 100)
              : (g.status === 'PASSED' ? 100 : 0);
            return (
              <div key={name} style={{ marginBottom: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '12px', color: '#c0c0e0' }}>{GATE_LABELS[name] || name}</span>
                  <span style={{
                    fontSize: '12px',
                    color: g.status === 'PASSED' ? '#30d030' : '#d03030',
                    fontWeight: 600,
                  }}>
                    {g.status} ({g.actual_value.toFixed(3)} / {g.threshold_value.toFixed(3)})
                  </span>
                </div>
                <div style={{ height: '8px', background: '#2a2a4a', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${Math.min(100, pct)}%`,
                    background: g.status === 'PASSED' ? '#30d030' : '#d03030',
                    borderRadius: '4px', transition: 'width 0.5s',
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {cert && (
        <div style={{ background: '#1a2a1a', borderRadius: '8px', padding: '16px',
                      border: '1px solid #2a5a2a', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: '#a0d0a0' }}>
            Certificate Issued
          </h3>
          <div style={{ fontSize: '12px', color: '#80b080', marginBottom: '4px' }}>
            ID: {cert.certificate_id?.slice(0, 8)}...
          </div>
          <div style={{ fontSize: '12px', color: '#80b080', marginBottom: '12px' }}>
            Issued: {cert.issued_at}
          </div>
          <div style={{ fontSize: '11px', color: '#608060' }}>
            {cert.limitations?.map((l, i) => (
              <div key={i} style={{ marginBottom: '2px' }}>{i + 1}. {l}</div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <button onClick={handleExport}
          disabled={!gradData?.is_graduated}
          style={{
            padding: '8px 20px', borderRadius: '8px', border: 'none',
            background: gradData?.is_graduated ? '#2a6a2a' : '#333',
            color: gradData?.is_graduated ? '#a0e0a0' : '#666',
            cursor: gradData?.is_graduated ? 'pointer' : 'not-allowed',
            fontWeight: 600, fontSize: '13px',
          }}>
          Export Strategy
        </button>

        {exportResult && (
          <div style={{ fontSize: '12px', color: '#80b080', marginTop: '8px', width: '100%' }}>
            Export complete: {exportResult.strategy_file}
          </div>
        )}

        {cert && (
          <>
            <a href={`http://localhost:8000/api/session/${session.sessionId}/download/strategy`}
              target="_blank" rel="noreferrer"
              style={{
                padding: '8px 20px', borderRadius: '8px', border: '1px solid #3a6ea5',
                background: '#1a1a3e', color: '#3a6ea5', textDecoration: 'none',
                fontWeight: 600, fontSize: '13px',
              }}>
              Download .py
            </a>
            <a href={`http://localhost:8000/api/session/${session.sessionId}/download/report`}
              target="_blank" rel="noreferrer"
              style={{
                padding: '8px 20px', borderRadius: '8px', border: '1px solid #3a6ea5',
                background: '#1a1a3e', color: '#3a6ea5', textDecoration: 'none',
                fontWeight: 600, fontSize: '13px',
              }}>
              Download PDF
            </a>
          </>
        )}
      </div>
    </div>
  );
}
