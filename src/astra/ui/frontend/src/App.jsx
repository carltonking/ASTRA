import React, { useState, useEffect } from 'react';
import Chat from './components/Chat';
import Dashboard from './components/Dashboard';
import useSession from './hooks/useSession';

export default function App() {
  const session = useSession();
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui, sans-serif', margin: 0 }}>
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
        background: '#1a1a2e', color: '#e0e0e0', padding: '6px 16px',
        fontSize: '12px', textAlign: 'center', letterSpacing: '1px',
        borderBottom: '1px solid #333',
      }}>
        RESEARCH PURPOSES ONLY — ASTRA v0.1.0 — Past performance does not predict future results
      </div>

      <div style={{ display: 'flex', width: '100%', height: '100vh', paddingTop: '28px' }}>
        <div style={{ width: '40%', borderRight: '1px solid #333', display: 'flex', flexDirection: 'column', background: '#0f0f23' }}>
          <Chat session={session} />
        </div>
        <div style={{ width: '60%', display: 'flex', flexDirection: 'column', background: '#16162a', overflow: 'auto' }}>
          <Dashboard session={session} activeTab={activeTab} onTabChange={setActiveTab} />
        </div>
      </div>
    </div>
  );
}
