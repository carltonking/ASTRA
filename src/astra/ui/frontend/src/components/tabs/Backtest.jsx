import React from 'react';

export default function Backtest({ session }) {
  const state = session.sessionState || {};
  const lastResult = state.pipeline_results?.[state.pipeline_results?.length - 1];
  const backtest = lastResult?.backtest_metrics || {};
  const cpcv = lastResult?.cpcv_summary || {};

  const Badge = ({ label, good }) => (
    <span style={{
      padding: '2px 8px', borderRadius: '10px', fontSize: '12px', fontWeight: 600,
      background: good ? '#1a3a1a' : '#3a1a1a',
      color: good ? '#30d030' : '#d03030',
      border: `1px solid ${good ? '#2a5a2a' : '#5a2a2a'}`,
    }}>
      {label}
    </span>
  );

  return (
    <div>
      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#e0e0e0' }}>
        Backtest Results
      </h2>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
        <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '12px 16px',
                      border: '1px solid #333', flex: 1 }}>
          <div style={{ fontSize: '11px', color: '#888', marginBottom: '4px' }}>Leakage</div>
          <Badge label={lastResult?.leakage_verdict || 'N/A'}
                 good={lastResult?.leakage_verdict === 'CLEAN'} />
        </div>
        <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '12px 16px',
                      border: '1px solid #333', flex: 1 }}>
          <div style={{ fontSize: '11px', color: '#888', marginBottom: '4px' }}>Review Board</div>
          <Badge label={lastResult?.review_board_status || 'N/A'}
                 good={lastResult?.review_board_status === 'APPROVED'} />
        </div>
      </div>

      <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px',
                    border: '1px solid #333' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#c0c0e0' }}>
          Performance Metrics
        </h3>
        <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #333', color: '#888' }}>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Metric</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Value</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Mean Sharpe Ratio', backtest.mean_sharpe],
              ['Deflated Sharpe Ratio', backtest.dsr],
              ['Overfitting Probability', backtest.overfitting_probability],
              ['CPCV Paths', cpcv.n_splits],
            ].map(([k, v]) => (
              <tr key={k} style={{ borderBottom: '1px solid #2a2a4a' }}>
                <td style={{ padding: '6px 8px', color: '#888' }}>{k}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', color: '#c0c0e0' }}>
                  {v != null ? (typeof v === 'number' ? v.toFixed(4) : v) : 'N/A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
