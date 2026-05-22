import React, { useState, useEffect } from 'react';
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

export default function Dashboard({ session }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [tabs, setTabs] = useState(() => loadTabOrder());
  const [customizing, setCustomizing] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs.map(t => t.id)));
  }, [tabs]);

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
        height: '44px', minHeight: '44px',
        display: 'flex', alignItems: 'center',
        padding: '0 8px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-base)',
        gap: '0',
      }}>
        {tabs.map((tab, idx) => {
          const active = activeTab === tab.id;
          return (
            <div key={tab.id} style={{ display: 'flex', alignItems: 'stretch', height: '100%' }}>
              <button onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: '0 14px',
                  fontSize: '12px', fontWeight: 500,
                  color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                  letterSpacing: '0.3px',
                  borderBottom: '2px solid ' + (active ? 'var(--accent)' : 'transparent'),
                  background: active ? 'var(--bg-surface)' : 'transparent',
                  transition: 'all 150ms ease',
                }}>
                {tab.label}
              </button>
              {customizing && (
                <div style={{ display: 'flex', gap: '1px', alignItems: 'center', marginLeft: '-2px' }}>
                  <button onClick={() => moveTab(idx, idx - 1)} disabled={idx === 0}
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '0 3px', fontSize: '9px', color: idx === 0 ? 'var(--text-faint)' : 'var(--text-muted)' }}>
                    {'<'}
                  </button>
                  <button onClick={() => moveTab(idx, idx + 1)} disabled={idx === tabs.length - 1}
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '0 3px', fontSize: '9px', color: idx === tabs.length - 1 ? 'var(--text-faint)' : 'var(--text-muted)' }}>
                    {'>'}
                  </button>
                </div>
              )}
            </div>
          );
        })}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px', paddingRight: '8px', alignItems: 'center' }}>
          {customizing && (
            <div style={{ display: 'flex', gap: '4px', alignItems: 'center', fontSize: '10px' }}>
              {ALL_TABS.filter(t => !tabs.find(v => v.id === t.id)).map(t => (
                <button key={t.id} onClick={() => toggleTab(t.id)}
                  className="btn btn-secondary btn-sm"
                  style={{ borderStyle: 'dashed', padding: '2px 8px', fontSize: '10px' }}>
                  +{t.label}
                </button>
              ))}
              {tabs.filter(t => tabs.length > 1).map(t => (
                <button key={`hide-${t.id}`} onClick={() => { toggleTab(t.id); if (activeTab === t.id) setActiveTab(tabs.find(v => v.id !== t.id)?.id || 'overview'); }}
                  style={{ background: 'none', border: 'none', color: 'var(--red)', cursor: 'pointer', fontSize: '10px', padding: '2px 4px', opacity: 0.6 }}
                  onMouseEnter={e => e.target.style.opacity = '1'}
                  onMouseLeave={e => e.target.style.opacity = '0.6'}>
                  x{t.label}
                </button>
              ))}
            </div>
          )}
          <button onClick={() => setCustomizing(!customizing)}
            className={`btn btn-sm ${customizing ? 'btn-primary' : 'btn-ghost'}`}
            style={{ padding: '2px 8px', fontSize: '11px' }}>
            {customizing ? 'Done' : '\u2699'}
          </button>
        </div>
      </div>

      <div style={{
        flex: 1, padding: '28px 32px', overflow: 'auto',
        background: 'var(--bg-base)',
      }}>
        {renderContent()}
      </div>
    </div>
  );
}
