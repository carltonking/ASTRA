import React from 'react';

export default function PaperTrading({ session }) {
  const state = session.sessionState || {};

  const DegBadge = ({ category }) => {
    const colors = {
      ACCEPTABLE: { bg: '#1a3a1a', fg: '#30d030', border: '#2a5a2a' },
      ELEVATED: { bg: '#3a3a1a', fg: '#d0d030', border: '#5a5a2a' },
      SEVERE: { bg: '#3a1a1a', fg: '#d03030', border: '#5a2a2a' },
    };
    const c = colors[category] || colors.ACCEPTABLE;
    return (
      <span style={{
        padding: '2px 8px', borderRadius: '10px', fontSize: '12px', fontWeight: 600,
        background: c.bg, color: c.fg, border: `1px solid ${c.border}`,
      }}>
        {category || 'N/A'}
      </span>
    );
  };

  return (
    <div>
      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', color: '#e0e0e0' }}>
        Paper Trading
        <span style={{ marginLeft: '8px', fontSize: '11px', color: '#888' }}>(Paper)</span>
      </h2>

      <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px',
                    border: '1px solid #333', marginBottom: '16px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#c0c0e0' }}>
          Performance
        </h3>
        <p style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
          Active paper trading session — deployment ID: {state.paper_deployment_id?.slice(0, 8) || 'N/A'}
        </p>
        <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #333', color: '#888' }}>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Metric</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Value</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Status', state.status || 'N/A'],
              ['Deployment', state.paper_deployment_id ? 'Active' : 'None'],
            ].map(([k, v]) => (
              <tr key={k} style={{ borderBottom: '1px solid #2a2a4a' }}>
                <td style={{ padding: '6px 8px', color: '#888' }}>{k}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', color: '#c0c0e0' }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ background: '#1a1a3e', borderRadius: '8px', padding: '16px',
                    border: '1px solid #333' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: '#c0c0e0' }}>
          Degradation
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', color: '#888' }}>Category:</span>
          <DegBadge category={state.degradation_category} />
        </div>
      </div>
    </div>
  );
}
