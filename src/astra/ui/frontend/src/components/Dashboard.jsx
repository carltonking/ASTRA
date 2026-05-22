import React, { useState, useEffect, useCallback } from 'react';
import Overview from './tabs/Overview';
import Backtest from './tabs/Backtest';
import PaperTrading from './tabs/PaperTrading';
import Optimization from './tabs/Optimization';
import Graduation from './tabs/Graduation';
import Comparison from './tabs/Comparison';

const ALL_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'paper_trading', label: 'Paper Trading' },
  { id: 'optimization', label: 'Optimization' },
  { id: 'graduation', label: 'Graduation' },
  { id: 'comparison', label: 'Comparison' },
];

const STORAGE_KEY = 'astra_dashboard_tabs';

function loadTabOrder() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(saved) && saved.length > 0) {
      return ALL_TABS.filter(t => saved.includes(t.id));
    }
  } catch {}
  return ALL_TABS;
}

function saveTabOrder(tabs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs.map(t => t.id)));
}

export default function Dashboard({ session }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [tabs, setTabs] = useState(() => loadTabOrder());
  const [customizing, setCustomizing] = useState(false);

  useEffect(() => { saveTabOrder(tabs); }, [tabs]);

  const toggleTab = (tabId) => {
    setTabs(prev => {
      const exists = prev.find(t => t.id === tabId);
      if (exists) return prev.filter(t => t.id !== tabId);
      const full = ALL_TABS.find(t => t.id === tabId);
      return full ? [...prev, full] : prev;
    });
  };

  const moveTab = (fromIdx, toIdx) => {
    if (toIdx < 0 || toIdx >= tabs.length) return;
    setTabs(prev => {
      const next = [...prev];
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      return next;
    });
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'overview': return <Overview session={session} />;
      case 'backtest': return <Backtest session={session} />;
      case 'paper_trading': return <PaperTrading session={session} isActive={activeTab === 'paper_trading'} />;
      case 'optimization': return <Optimization session={session} />;
      case 'graduation': return <Graduation session={session} />;
      case 'comparison': return <Comparison session={session} />;
      default: return null;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        height: '40px', minHeight: '40px',
        display: 'flex', alignItems: 'center', gap: '0',
        padding: '0 4px',
        borderBottom: '1px solid #1e1e1e',
        background: '#0a0a0a',
      }}>
        {tabs.map((tab, idx) => {
          const active = activeTab === tab.id;
          return (
            <div key={tab.id} style={{ display: 'flex', alignItems: 'center' }}>
              <button onClick={() => setActiveTab(tab.id)}
                style={{
                  height: '40px', padding: '0 12px', cursor: 'pointer',
                  fontSize: '13px', fontWeight: 500,
                  color: active ? '#e8e8e8' : '#555',
                  background: 'transparent', border: 'none',
                  borderBottom: `2px solid ${active ? '#fff' : 'transparent'}`,
                  letterSpacing: '0.2px', whiteSpace: 'nowrap',
                }}>
                {tab.label}
              </button>
              {customizing && (
                <div style={{ display: 'flex', gap: '2px', marginRight: '4px' }}>
                  <button onClick={() => moveTab(idx, idx - 1)} disabled={idx === 0}
                    style={{ background: 'none', border: 'none', color: idx === 0 ? '#333' : '#555', cursor: idx === 0 ? 'default' : 'pointer', fontSize: '10px', padding: '0 2px' }}>
                    {'<'}
                  </button>
                  <button onClick={() => moveTab(idx, idx + 1)} disabled={idx === tabs.length - 1}
                    style={{ background: 'none', border: 'none', color: idx === tabs.length - 1 ? '#333' : '#555', cursor: idx === tabs.length - 1 ? 'default' : 'pointer', fontSize: '10px', padding: '0 2px' }}>
                    {'>'}
                  </button>
                </div>
              )}
            </div>
          );
        })}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px', paddingRight: '8px' }}>
          {customizing && (
            <div style={{ display: 'flex', gap: '4px', alignItems: 'center', fontSize: '11px' }}>
              {ALL_TABS.filter(t => !tabs.find(v => v.id === t.id)).map(t => (
                <button key={t.id} onClick={() => toggleTab(t.id)}
                  style={{ background: 'none', border: '1px dashed #333', color: '#555', cursor: 'pointer', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                  +{t.label}
                </button>
              ))}
              {tabs.filter(t => tabs.length > 1).map(t => (
                <button key={`hide-${t.id}`} onClick={() => { toggleTab(t.id); if (activeTab === t.id) setActiveTab(tabs.find(v => v.id !== t.id)?.id || 'overview'); }}
                  style={{ background: 'none', border: 'none', color: '#ef5350', cursor: 'pointer', fontSize: '10px', padding: '2px 4px' }}>
                  x{t.label}
                </button>
              ))}
            </div>
          )}
          <button onClick={() => setCustomizing(!customizing)}
            style={{ background: 'none', border: 'none', color: customizing ? '#e8e8e8' : '#555', cursor: 'pointer', fontSize: '13px', padding: '2px 6px' }}>
            {customizing ? 'Done' : '\u2699'}
          </button>
        </div>
      </div>

      <div style={{
        flex: 1, padding: '24px', overflow: 'auto',
        background: '#0a0a0a', color: '#ccc', fontSize: '13px', lineHeight: 1.6,
      }}>
        {renderContent()}
      </div>
    </div>
  );
}
