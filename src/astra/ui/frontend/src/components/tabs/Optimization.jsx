import React from 'react';

export default function Optimization({ session }) {
  const state = session.sessionState || {};
  const results = state.pipeline_results || [];

  return (
    <div>
      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#e0e0e0' }}>
        Optimization Cycles
      </h2>

      {results.length === 0 ? (
        <div style={{ color: '#666', fontStyle: 'italic', padding: '20px', textAlign: 'center' }}>
          No optimization cycles yet. Strategy must be deployed first.
        </div>
      ) : (
        <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px',
                      border: '1px solid #333' }}>
          <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #333', color: '#888' }}>
                <th style={{ padding: '6px 8px', textAlign: 'left' }}>Cycle</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>Sharpe</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>DSR</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #2a2a4a' }}>
                  <td style={{ padding: '6px 8px', color: '#c0c0e0' }}>{r.cycle_number || i + 1}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: '#c0c0e0' }}>
                    {r.backtest_metrics?.mean_sharpe?.toFixed(2) || 'N/A'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: '#c0c0e0' }}>
                    {r.cpcv_summary?.dsr?.toFixed(2) || 'N/A'}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      padding: '1px 6px', borderRadius: '8px', fontSize: '11px',
                      background: r.status === 'DEPLOYED_PAPER' ? '#1a3a1a' : '#3a1a1a',
                      color: r.status === 'DEPLOYED_PAPER' ? '#30d030' : '#d03030',
                    }}>
                      {r.status || 'PENDING'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
