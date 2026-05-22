import React, { useState, useEffect, useCallback } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import useAlpaca from '../../hooks/useAlpaca';

/* ─── shared sub-components ─── */

function Section({ title, children, action, lastUpdated, onRefresh }) {
  const secs = lastUpdated ? Math.floor((Date.now() - lastUpdated.getTime()) / 1000) : null;
  return (
    <div style={{ background: '#161616', border: '1px solid #1e1e1e', borderRadius: '8px', padding: '20px', marginBottom: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8' }}>{title}</span>
          {secs !== null && <span style={{ fontSize: '10px', color: '#444' }}>{secs}s ago</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {action}
          {onRefresh && (
            <button onClick={onRefresh} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: '13px', padding: '2px', lineHeight: 1 }} title="Refresh">
              &#x21bb;
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

function Pill({ label, color, bg, border }) {
  return (
    <span style={{
      padding: '2px 8px', borderRadius: '9999px', fontSize: '11px', fontWeight: 500,
      border: `1px solid ${border || '#333'}`,
      color: color || '#888',
      background: bg || 'transparent',
    }}>
      {label}
    </span>
  );
}

function FormattedNumber({ value, decimals = 2, prefix = '', mono = true }) {
  const n = parseFloat(value);
  if (isNaN(n)) return <span style={{ color: '#555' }}>&mdash;</span>;
  const color = n > 0 ? '#22c55e' : n < 0 ? '#ef5350' : '#e8e8e8';
  return (
    <span style={{
      color, fontFamily: mono ? "'JetBrains Mono', 'Fira Code', monospace" : undefined,
      fontSize: '14px', fontWeight: 500,
    }}>
      {prefix}{n.toFixed(decimals)}
    </span>
  );
}

/* ─── config form ─── */

function ConfigForm({ apiKeyId, apiSecret, onSave }) {
  const [k, setK] = useState(apiKeyId);
  const [s, setS] = useState(apiSecret);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8', marginBottom: '4px' }}>Paper Trading</div>
      <div style={{ fontSize: '12px', color: '#555', marginBottom: '8px' }}>Connect your Alpaca paper trading account to get started.</div>
      <input placeholder="API Key ID" value={k} onChange={e => setK(e.target.value)}
        style={{ padding: '9px 14px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '13px' }} />
      <input placeholder="Secret Key" type="password" value={s} onChange={e => setS(e.target.value)}
        style={{ padding: '9px 14px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '13px' }} />
      <button onClick={() => onSave(k.trim(), s.trim())}
        style={{ alignSelf: 'flex-start', padding: '8px 20px', borderRadius: '6px', border: '1px solid #2e2e2e', background: 'transparent', color: '#aaa', fontSize: '13px', cursor: 'pointer' }}>
        Connect
      </button>
    </div>
  );
}

/* ─── main component ─── */

export default function PaperTrading({ session, isActive }) {
  const alpaca = useAlpaca({ enabled: isActive });

  if (!alpaca.configured) {
    return (
      <div style={{ padding: '40px 0' }}>
        <div style={{ fontSize: '20px', fontWeight: 600, color: '#e8e8e8', marginBottom: '12px' }}>Paper Trading</div>
        <div style={{ fontSize: '12px', color: '#555', marginBottom: '8px' }}>
          Paper trading requires a broker to be configured in ASTRA's backend (.env file).
        </div>
        <div style={{ fontSize: '12px', color: '#555' }}>
          Set APCA_API_KEY_ID and APCA_API_SECRET_KEY for Alpaca paper trading.
          Keys are now served from the backend — no browser exposure.
        </div>
      </div>
    );
  }

  return (
    <div>
      <PortfolioChart alpaca={alpaca} />
      <Balances alpaca={alpaca} />
      <TopPositions alpaca={alpaca} />
      <RecentOrders alpaca={alpaca} />
      {session && <MonitoringStatus sessionId={session.session_id} />}
      {session && <GraduationSection sessionId={session.session_id} />}
    </div>
  );
}

/* ─── SECTION 5: Monitoring Status (auto-refresh every 30s) ─── */

function MonitoringStatus({ sessionId }) {
  const [monitoring, setMonitoring] = useState(null);
  const fetchMonitoring = useCallback(() => {
    if (!sessionId) return;
    fetch(`/api/broker/monitoring?session_id=${sessionId}`)
      .then(r => r.json())
      .then(d => setMonitoring(d))
      .catch(() => {});
  }, [sessionId]);
  useEffect(() => {
    fetchMonitoring();
    const id = setInterval(fetchMonitoring, 30000);
    return () => clearInterval(id);
  }, [fetchMonitoring]);
  if (!monitoring || monitoring.status === 'no_data') return null;
  return (
    <Section title="Monitoring">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
        <div>
          <div style={{ fontSize: '11px', color: '#555', marginBottom: '4px' }}>Status</div>
          <span style={{ color: monitoring.status === 'PAPER_TRADING' ? '#22c55e' : '#888', fontSize: '13px', fontWeight: 500 }}>{monitoring.status}</span>
        </div>
        <div>
          <div style={{ fontSize: '11px', color: '#555', marginBottom: '4px' }}>Cycle</div>
          <span style={{ color: '#e8e8e8', fontSize: '13px', fontWeight: 500 }}>{monitoring.cycle_number || 0}</span>
        </div>
        <div>
          <div style={{ fontSize: '11px', color: '#555', marginBottom: '4px' }}>Deployment</div>
          <span style={{ color: '#888', fontSize: '12px', fontFamily: 'monospace' }}>{monitoring.deployment_id ? monitoring.deployment_id.substring(0, 8) + '...' : 'N/A'}</span>
        </div>
      </div>
      {monitoring.cpcv_summary && (
        <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', padding: '12px', background: '#ffffff08', borderRadius: '6px' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#555' }}>Sharpe</div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8' }}>{(monitoring.cpcv_summary.mean_sharpe || 0).toFixed(2)}</div>
          </div>
          <div>
            <div style={{ fontSize: '10px', color: '#555' }}>DSR</div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8' }}>{(monitoring.cpcv_summary.dsr || 0).toFixed(2)}</div>
          </div>
          <div>
            <div style={{ fontSize: '10px', color: '#555' }}>Ann. Return</div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: '#22c55e' }}>{(monitoring.cpcv_summary.annualized_return || 0 * 100).toFixed(1)}%</div>
          </div>
          <div>
            <div style={{ fontSize: '10px', color: '#555' }}>Win Rate</div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: '#e8e8e8' }}>{(monitoring.cpcv_summary.win_rate || 0 * 100).toFixed(1)}%</div>
          </div>
        </div>
      )}
    </Section>
  );
}

/* ─── SECTION 6: Graduation (inline from Graduation.jsx) ─── */

function GraduationSection({ sessionId }) {
  const [grad, setGrad] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportStep, setExportStep] = useState(0);
  const EXPORT_STEPS = ['validate', 'package', 'report', 'checksum', 'done'];

  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/session/${sessionId}/graduation`)
      .then(r => r.json())
      .then(d => setGrad(d))
      .catch(() => {});
  }, [sessionId]);

  if (!grad || !grad.is_graduated) return null;

  const execExport = async () => {
    setExporting(true);
    for (let i = 0; i < EXPORT_STEPS.length; i++) {
      setExportStep(i + 1);
      await new Promise(r => setTimeout(r, 600));
    }
    try {
      const res = await fetch(`/api/session/${sessionId}/export`, { method: 'POST' });
      const data = await res.json();
      if (data.strategy_file) window.open(`/api/session/${sessionId}/download/strategy`, '_blank');
      if (data.report_file) window.open(`/api/session/${sessionId}/download/report`, '_blank');
    } catch (_) {}
    setExporting(false);
    setExportStep(0);
  };

  const certId = grad.certificate?.certificate_id || `ASTRA-${sessionId?.substring(0, 8)}-GRAD`;
  const issuedAt = grad.certificate?.issued_at || grad.certificate?.issued_date || '';

  return (
    <Section title="Graduation">
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px' }}>
        <div>
          <div style={{ fontSize: '11px', color: '#555', marginBottom: '4px' }}>Certificate</div>
          <div style={{ fontFamily: 'monospace', fontSize: '12px', color: '#22c55e', marginBottom: '8px' }}>{certId}</div>
          {issuedAt && (
            <div style={{ fontSize: '11px', color: '#888' }}>Issued: {new Date(issuedAt).toLocaleDateString()}</div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center' }}>
          {!exporting ? (
            <button onClick={execExport}
              style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #22c55e40', background: '#22c55e15', color: '#22c55e', fontSize: '13px', cursor: 'pointer' }}>
              Export Strategy
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              {EXPORT_STEPS.map((s, i) => (
                <div key={s} style={{
                  width: '24px', height: '24px', borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '10px', fontWeight: 500,
                  background: i < exportStep ? '#22c55e30' : '#ffffff08',
                  color: i < exportStep ? '#22c55e' : '#555',
                  border: `1px solid ${i < exportStep ? '#22c55e40' : '#2a2a2a'}`,
                }}>
                  {i + 1}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}

/* ─── SECTION 1: Portfolio Chart ─── */

const PERIODS = [
  { label: '1D', period: '1D', tf: '5Min' },
  { label: '1M', period: '1M', tf: '1H' },
  { label: '1Y', period: '1Y', tf: '1D' },
  { label: 'All', period: 'All', tf: '1D' },
];

function PortfolioChart({ alpaca }) {
  const [activePeriod, setActivePeriod] = useState('1D');
  const [localHistory, setLocalHistory] = useState(null);

  const load = useCallback((period, tf) => {
    alpaca.fetchPortfolioHistory(period, tf).then(d => setLocalHistory(d));
  }, [alpaca]);

  const switchPeriod = (p, tf) => {
    setActivePeriod(p);
    load(p, tf);
  };

  const history = localHistory || alpaca.portfolioHistory;
  const timestamps = history?.timestamp || [];
  const equity = history?.equity || [];
  const chartData = timestamps.map((ts, i) => ({
    time: new Date(ts * 1000).toLocaleDateString(),
    equity: parseFloat(equity[i]),
  }));
  const latestEquity = equity.length ? equity[equity.length - 1] : null;
  const latestTime = timestamps.length ? new Date(timestamps[timestamps.length - 1] * 1000) : null;

  return (
    <Section title="Portfolio" lastUpdated={alpaca.lastUpdated} onRefresh={() => load(activePeriod, PERIODS.find(p => p.label === activePeriod)?.tf || '5Min')}>
      {/* Equity value */}
      <div style={{ marginBottom: '4px' }}>
        <span style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: '24px', fontWeight: 500, color: '#e8e8e8' }}>
          {latestEquity ? `$${parseFloat(latestEquity).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '\u2014'}
        </span>
      </div>
      {latestTime && <div style={{ fontSize: '11px', color: '#555', marginBottom: '16px' }}>{latestTime.toLocaleString()}</div>}

      {/* Period toggle */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
        {PERIODS.map(({ label, period, tf }) => (
          <button key={label} onClick={() => switchPeriod(period, tf)}
            style={{
              padding: '4px 14px', borderRadius: '4px', border: '1px solid',
              borderColor: activePeriod === label ? '#333' : 'transparent',
              background: activePeriod === label ? '#1e1e1e' : 'transparent',
              color: activePeriod === label ? '#e8e8e8' : '#555',
              fontSize: '12px', cursor: 'pointer', fontWeight: 500,
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div style={{ width: '100%', height: '240px' }}>
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 2" stroke="#1e1e1e" vertical={false} />
              <XAxis dataKey="time" stroke="#444" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis stroke="#444" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} domain={['dataMin', 'dataMax']} tickFormatter={v => `$${v.toLocaleString()}`} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: '4px', fontSize: '11px' }} />
              <Area type="monotone" dataKey="equity" stroke="#ffffff" strokeWidth={1.5} fill="url(#portfolioGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#444', fontSize: '11px' }}>Loading portfolio data...</div>
        )}
      </div>
    </Section>
  );
}

/* ─── SECTION 2: Balances ─── */

function Balances({ alpaca }) {
  const a = alpaca.account;
  if (!a) return null;

  const dailyChange = parseFloat(a.equity) - parseFloat(a.last_equity);
  const changeColor = dailyChange > 0 ? '#22c55e' : dailyChange < 0 ? '#ef5350' : '#e8e8e8';

  const col = (label, value, color) => (
    <div>
      <div style={{ fontSize: '12px', color: '#555', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '14px', fontWeight: 500, color: color || '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>{value}</div>
    </div>
  );

  return (
    <Section title="Balances" lastUpdated={alpaca.lastUpdated} onRefresh={alpaca.fetchAccount}
      action={
        <button onClick={alpaca.fetchAccount}
          style={{ width: '24px', height: '24px', borderRadius: '50%', border: '1px solid #333', background: 'transparent', color: '#555', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', lineHeight: 1 }}>
          &#x21bb;
        </button>
      }>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
        {col('Buying Power', `$${parseFloat(a.buying_power).toLocaleString(undefined, { minimumFractionDigits: 2 })}`)}
        {col('Cash', `$${parseFloat(a.cash).toLocaleString(undefined, { minimumFractionDigits: 2 })}`)}
        {col('Daily Change', `${dailyChange >= 0 ? '+' : ''}$${dailyChange.toFixed(2)}`, changeColor)}
      </div>
    </Section>
  );
}

/* ─── SECTION 3: Top Positions ─── */

function TopPositions({ alpaca }) {
  const [filter, setFilter] = useState('all');
  const positions = alpaca.positions || [];

  const filtered = filter === 'all' ? positions : positions.filter(p => {
    const pl = parseFloat(p.unrealized_pl);
    return filter === 'win' ? pl >= 0 : pl < 0;
  });

  const headerStyle = { padding: '8px 12px', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#555', fontWeight: 500, textAlign: 'right', background: '#111', borderBottom: '1px solid #1e1e1e' };
  const headerLeft = { ...headerStyle, textAlign: 'left' };

  return (
    <Section title="Top Positions" lastUpdated={alpaca.lastUpdated} onRefresh={alpaca.fetchPositions}
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <select value={filter} onChange={e => setFilter(e.target.value)}
            style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid #2a2a2a', background: '#161616', color: '#aaa', fontSize: '12px', outline: 'none' }}>
            <option value="all">All</option>
            <option value="win">Winners</option>
            <option value="loss">Losers</option>
          </select>
          <span style={{ fontSize: '11px', color: '#555', cursor: 'pointer' }}>View All</span>
        </div>
      }>
      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#444', fontSize: '12px', fontStyle: 'italic' }}>
          No open positions
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr>
                <th style={headerLeft}>Asset</th>
                <th style={headerStyle}>Price</th>
                <th style={headerStyle}>Qty</th>
                <th style={headerStyle}>Market Value</th>
                <th style={headerStyle}>P/L</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => {
                const pl = parseFloat(p.unrealized_pl);
                return (
                  <tr key={p.asset_id || p.symbol} style={{ borderBottom: '1px solid #1a1a1a' }}>
                    <td style={{ padding: '10px 12px', color: '#e8e8e8' }}>{p.symbol}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>${parseFloat(p.current_price).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>{parseFloat(p.qty).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>${parseFloat(p.market_value).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: "'JetBrains Mono', 'Fira Code', monospace", color: pl >= 0 ? '#22c55e' : '#ef5350' }}>
                      {pl >= 0 ? '+' : ''}${pl.toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

/* ─── SECTION 4: Recent Orders ─── */

const PAGE_SIZE = 10;

function RecentOrders({ alpaca }) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState({});
  const [page, setPage] = useState(0);
  const [cancelBusy, setCancelBusy] = useState(false);

  const orders = alpaca.orders || [];

  const searched = search.trim()
    ? orders.filter(o => o.symbol?.toLowerCase().includes(search.toLowerCase()))
    : orders;

  const totalPages = Math.max(1, Math.ceil(searched.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageOrders = searched.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const toggleSelect = (id) => setSelected(prev => ({ ...prev, [id]: !prev[id] }));
  const selectAll = () => {
    if (pageOrders.every(o => selected[o.id])) {
      setSelected({});
    } else {
      const all = {};
      pageOrders.forEach(o => { all[o.id] = true; });
      setSelected(all);
    }
  };

  const cancelSelected = async () => {
    setCancelBusy(true);
    const ids = Object.entries(selected).filter(([, v]) => v).map(([id]) => id);
    for (const id of ids) {
      try { await alpaca.cancelOrder(id); } catch (_) {}
    }
    setSelected({});
    setCancelBusy(false);
  };

  const statusStyle = (status) => {
    const s = status?.toLowerCase() || '';
    if (s === 'filled') return { color: '#22c55e', border: '1px solid #22c55e30', bg: '#22c55e15' };
    if (s === 'canceled' || s === 'cancelled') return { color: '#ef5350', border: '1px solid #ef535030', bg: '#ef535015' };
    return { color: '#888', border: '1px solid #333', bg: '#ffffff10' };
  };

  const th = { padding: '8px 10px', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#555', fontWeight: 500, textAlign: 'right', background: '#111', borderBottom: '1px solid #1e1e1e' };
  const thLeft = { ...th, textAlign: 'left' };
  const thCenter = { ...th, textAlign: 'center' };

  return (
    <Section title="Recent Orders" lastUpdated={alpaca.lastUpdated} onRefresh={() => alpaca.fetchOrders()}
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#555', fontSize: '11px', pointerEvents: 'none' }}>&#x1F50D;</span>
            <input placeholder="Search" value={search} onChange={e => setSearch(e.target.value)}
              style={{ padding: '6px 10px 6px 28px', borderRadius: '8px', border: '1px solid #2a2a2a', background: '#161616', color: '#e8e8e8', fontSize: '12px', outline: 'none', width: '140px' }} />
          </div>
          {Object.values(selected).some(Boolean) && (
            <button onClick={cancelSelected} disabled={cancelBusy}
              style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid #2a2a2a', background: 'transparent', color: '#888', fontSize: '11px', cursor: 'pointer' }}>
              Cancel {Object.values(selected).filter(Boolean).length} selected
            </button>
          )}
        </div>
      }>
      {searched.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#444', fontSize: '12px', fontStyle: 'italic' }}>
          No orders found
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr>
                  <th style={{ ...thCenter, width: '32px' }}>
                    <input type="checkbox" checked={pageOrders.length > 0 && pageOrders.every(o => selected[o.id])}
                      onChange={selectAll}
                      style={{ accentColor: '#fff', cursor: 'pointer' }} />
                  </th>
                  <th style={thLeft}>Asset</th>
                  <th style={th}>Type</th>
                  <th style={th}>Side</th>
                  <th style={th}>Qty</th>
                  <th style={th}>Filled</th>
                  <th style={th}>Avg Fill</th>
                  <th style={th}>Status</th>
                </tr>
              </thead>
              <tbody>
                {pageOrders.map(o => {
                  const ss = statusStyle(o.status);
                  return (
                    <tr key={o.id} style={{ borderBottom: '1px solid #1a1a1a' }}>
                      <td style={{ padding: '10px 6px', textAlign: 'center' }}>
                        <input type="checkbox" checked={!!selected[o.id]} onChange={() => toggleSelect(o.id)}
                          style={{ accentColor: '#fff', cursor: 'pointer' }} />
                      </td>
                      <td style={{ padding: '10px 10px', color: '#e8e8e8' }}>{o.symbol}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: '#888' }}>{o.type}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: o.side === 'buy' ? '#22c55e' : '#ef5350' }}>{o.side}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>{o.qty}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>{o.filled_qty || '0'}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: '#e8e8e8', fontFamily: "'JetBrains Mono', 'Fira Code', monospace" }}>{o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toFixed(2)}` : '\u2014'}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right' }}>
                        <Pill label={o.status} color={ss.color} border={ss.border} bg={ss.bg} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginTop: '16px' }}>
            <button onClick={() => setPage(Math.max(0, safePage - 1))} disabled={safePage === 0}
              style={{ padding: '4px 10px', borderRadius: '4px', border: '1px solid #1e1e1e', background: '#161616', color: safePage === 0 ? '#333' : '#888', cursor: safePage === 0 ? 'default' : 'pointer', fontSize: '12px' }}>
              Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => (
              <button key={i} onClick={() => setPage(i)}
                style={{
                  padding: '4px 10px', borderRadius: '4px', border: '1px solid #1e1e1e', fontSize: '12px', cursor: 'pointer',
                  background: i === safePage ? '#1e1e1e' : '#161616',
                  color: i === safePage ? '#e8e8e8' : '#888',
                }}>
                {i + 1}
              </button>
            ))}
            <button onClick={() => setPage(Math.min(totalPages - 1, safePage + 1))} disabled={safePage === totalPages - 1}
              style={{ padding: '4px 10px', borderRadius: '4px', border: '1px solid #1e1e1e', background: '#161616', color: safePage === totalPages - 1 ? '#333' : '#888', cursor: safePage === totalPages - 1 ? 'default' : 'pointer', fontSize: '12px' }}>
              Next
            </button>
          </div>
        </>
      )}
    </Section>
  );
}
