import React from 'react';
import Overview from './tabs/Overview';
import Backtest from './tabs/Backtest';
import PaperTrading from './tabs/PaperTrading';
import Optimization from './tabs/Optimization';
import Graduation from './tabs/Graduation';

const TABS = ['overview', 'backtest', 'paper_trading', 'optimization', 'graduation'];
const TAB_LABELS = {
  overview: 'Overview', backtest: 'Backtest', paper_trading: 'Paper Trading',
  optimization: 'Optimization', graduation: 'Graduation',
};

export default function Dashboard({ session, activeTab, onTabChange }) {
  const tabStyle = (tab) => ({
    padding: '8px 16px', cursor: 'pointer', fontSize: '13px', fontWeight: 500,
    borderBottom: activeTab === tab ? '2px solid #3a6ea5' : '2px solid transparent',
    color: activeTab === tab ? '#3a6ea5' : '#888',
    background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid #3a6ea5' : '2px solid transparent',
    outline: 'none',
  });

  const renderTab = () => {
    switch (activeTab) {
      case 'overview': return <Overview session={session} />;
      case 'backtest': return <Backtest session={session} />;
      case 'paper_trading': return <PaperTrading session={session} />;
      case 'optimization': return <Optimization session={session} />;
      case 'graduation': return <Graduation session={session} />;
      default: return null;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', gap: '4px', padding: '8px 16px 0',
                    borderBottom: '1px solid #333', background: '#1a1a2e' }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => onTabChange(tab)} style={tabStyle(tab)}>
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, padding: '16px', overflow: 'auto', color: '#c0c0d0', fontSize: '14px' }}>
        {renderTab()}
      </div>
      <div style={{ padding: '6px 16px', borderTop: '1px solid #333', fontSize: '11px',
                    color: '#666', textAlign: 'center', background: '#0f0f23' }}>
        RESEARCH PURPOSES ONLY — Past performance does not predict future results
      </div>
    </div>
  );
}
