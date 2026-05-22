import React from 'react';

const spinnerStyle = {
  display: 'inline-block',
  width: '20px',
  height: '20px',
  border: '2px solid var(--border, #333)',
  borderTopColor: 'var(--accent, #3a6ea5)',
  borderRadius: '50%',
  animation: 'astra-spin 0.7s linear infinite',
};

const keyframesStyle = `
@keyframes astra-spin {
  to { transform: rotate(360deg); }
}
@keyframes astra-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
`;

export function Spinner({ size = 20, style }) {
  return (
    <>
      <style>{keyframesStyle}</style>
      <span style={{ ...spinnerStyle, width: size, height: size, ...style }} />
    </>
  );
}

export function LoadingOverlay({ text = 'Loading...' }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '60px 20px', gap: '16px', color: 'var(--text-muted, #888)', fontSize: '13px',
    }}>
      <Spinner size={28} />
      <span>{text}</span>
    </div>
  );
}

export function Skeleton({ width = '100%', height = '16px', style }) {
  return (
    <>
      <style>{keyframesStyle}</style>
      <div style={{
        width, height, borderRadius: '4px',
        background: 'var(--bg-hover, #2a2a4a)',
        animation: 'astra-pulse 1.5s ease-in-out infinite',
        ...style,
      }} />
    </>
  );
}
