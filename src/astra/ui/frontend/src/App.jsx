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
      const isOpen = day >= 1 && day <= 5 && hours >= 9.5 && hours < 16;
      setOpen(isOpen);
    };
    check();
    const id = setInterval(check, 60000);
    return () => clearInterval(id);
  }, []);
  if (open === null) return null;
  return (
    <span style={{
      fontSize: '10px', padding: '2px 8px', borderRadius: '9999px',
      color: open ? '#22c55e' : '#ef5350',
      border: `1px solid ${open ? '#22c55e30' : '#ef535030'}`,
      background: open ? '#22c55e10' : '#ef535010',
      marginLeft: '8px',
    }}>
      {open ? 'OPEN' : 'CLOSED'}
    </span>
  );
}

export default function App() {
  const session = useSession();
  const { connected } = useWebSocket(session.sessionId);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0a0a0a' }}>
      {/* Left sidebar — 400px fixed */}
      <div style={{
        width: collapsed ? '0px' : '400px', minWidth: collapsed ? '0px' : '400px',
        display: 'flex', flexDirection: 'column',
        borderRight: collapsed ? 'none' : '1px solid #1e1e1e',
        overflow: 'hidden', transition: 'width 100ms ease',
      }}>
        {/* 40px navbar */}
        <div style={{
          height: '40px', minHeight: '40px',
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '0 16px', borderBottom: '1px solid #1e1e1e',
          background: '#0a0a0a',
        }}>
          <span style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: connected ? '#22c55e' : '#444',
            flexShrink: 0, display: 'inline-block',
          }} />
          <span style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8', letterSpacing: '0.3px' }}>
            A.S.T.R.A.
          </span>
          <MarketHours />
          <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#666' }}>
            {session.sessionId ? (connected ? 'connected' : 'offline') : ''}
          </span>
          <button onClick={() => setCollapsed(!collapsed)}
            style={{
              background: 'none', border: 'none', color: '#666', cursor: 'pointer',
              padding: '4px', fontSize: '12px', lineHeight: 1,
            }}>
            {collapsed ? '\u203A' : '\u2039'}
          </button>
        </div>

        {/* Chat body */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Chat session={session} />
        </div>
      </div>

      {/* Collapsed toggle tab */}
      {collapsed && (
        <button onClick={() => setCollapsed(false)}
          style={{
            width: '20px', alignSelf: 'center',
            background: '#0a0a0a', border: '1px solid #1e1e1e', borderLeft: 'none',
            color: '#666', cursor: 'pointer', padding: '8px 0', fontSize: '11px',
            borderRadius: '0 4px 4px 0',
          }}>
          {'>'}
        </button>
      )}

      {/* Right panel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Dashboard session={session} />
      </div>

      <ToastContainer position="bottom-right" theme="dark" />
    </div>
  );
}
