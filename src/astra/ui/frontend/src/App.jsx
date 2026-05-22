import React, { useState, useEffect } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import useSession from './hooks/useSession';
import useWebSocket from './hooks/useWebSocket';
import Chat from './components/Chat';
import Dashboard from './components/Dashboard';

function MarketHours() {
  const [open, setOpen] = useState(null);
  useEffect(() => {
    const check = () => {
      const now = new Date();
      const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = et.getDay();
      const hours = et.getHours() + et.getMinutes() / 60;
      setOpen(day >= 1 && day <= 5 && hours >= 9.5 && hours < 16);
    };
    check();
    const id = setInterval(check, 60000);
    return () => clearInterval(id);
  }, []);
  if (open === null) return null;
  return <span className={`badge ${open ? 'badge-green' : 'badge-red'}`}>{open ? 'OPEN' : 'CLOSED'}</span>;
}

export default function App() {
  const session = useSession();
  const { connected } = useWebSocket(session.sessionId);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <div style={{
        width: collapsed ? '0px' : '380px', minWidth: collapsed ? '0px' : '380px',
        display: 'flex', flexDirection: 'column',
        borderRight: collapsed ? 'none' : '1px solid var(--border)',
        overflow: 'hidden', transition: 'width 150ms ease, min-width 150ms ease',
        background: 'var(--bg-surface)',
      }}>
        <div style={{
          height: '44px', minHeight: '44px',
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '0 16px',
          borderBottom: '1px solid var(--border)',
        }}>
          <span style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: connected ? 'var(--green)' : 'var(--text-dim)',
            flexShrink: 0, display: 'inline-block',
            boxShadow: connected ? '0 0 6px rgba(34,197,94,0.4)' : 'none',
          }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '1px' }}>
            ASTRA
          </span>
          <MarketHours />
          <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.3px' }}>
            {session.sessionId ? (connected ? 'CONNECTED' : 'OFFLINE') : ''}
          </span>
          <button onClick={() => setCollapsed(!collapsed)} className="btn btn-ghost btn-sm">
            {collapsed ? '\u203A' : '\u2039'}
          </button>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Chat session={session} />
        </div>
      </div>

      {collapsed && (
        <button onClick={() => setCollapsed(false)}
          style={{
            width: '20px', alignSelf: 'center', cursor: 'pointer',
            background: 'var(--bg-surface)', border: '1px solid var(--border)', borderLeft: 'none',
            color: 'var(--text-secondary)', padding: '8px 0', fontSize: '11px',
            borderRadius: '0 6px 6px 0',
          }}>
          {'>'}
        </button>
      )}

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Dashboard session={session} />
      </div>

      <ToastContainer position="bottom-right" theme="dark" />
    </div>
  );
}
