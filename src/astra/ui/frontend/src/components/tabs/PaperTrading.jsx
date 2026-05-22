import React, { useState, useEffect, useCallback } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import useAlpaca from '../../hooks/useAlpaca';

/* ─── shared sub-components ─── */

function Section({ title, children, action, lastUpdated, onRefresh }) {
  const secs = lastUpdated ? Math.floor((Date.now() - lastUpdated.getTime()) / 1000) : null;
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-sm)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
          <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>{title}</span>
          {secs !== null && <span style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-faint)' }}>{secs}s ago</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
          {action}
          {onRefresh && (
            <button onClick={onRefresh} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 'var(--font-size-sm)', padding: '2px', lineHeight: 1 }} title="Refresh">
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
      padding: '2px 8px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)', fontWeight: 500,
      border: `1px solid ${border || 'var(--border)'}`,
      color: color || 'var(--text-muted)',
      background: bg || 'transparent',
    }}>
      {label}
    </span>
  );
}

function FormattedNumber({ value, decimals = 2, prefix = '', mono = true }) {
  const n = parseFloat(value);
  if (isNaN(n)) return <span style={{ color: 'var(--text-dim)' }}>&mdash;</span>;
  const color = n > 0 ? 'var(--green)' : n < 0 ? 'var(--red)' : 'var(--text-primary)';
  return (
    <span style={{
      color, fontFamily: mono ? 'var(--font-mono)' : undefined,
      fontSize: 'var(--font-size-md)', fontWeight: 500,
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
      <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-xs)' }}>Paper Trading</div>
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Connect your Alpaca paper trading account to get started.</div>
      <input placeholder="API Key ID" value={k} onChange={e => setK(e.target.value)}
        style={{ padding: '9px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)' }} />
      <input placeholder="Secret Key" type="password" value={s} onChange={e => setS(e.target.value)}
        style={{ padding: '9px 14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)' }} />
      <button onClick={() => onSave(k.trim(), s.trim())}
        style={{ alignSelf: 'flex-start', padding: 'var(--space-xs) var(--space-md)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-size-sm)', cursor: 'pointer' }}>
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
        <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Paper Trading</div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>
          Paper trading requires a broker to be configured in ASTRA's backend (.env file).
        </div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)' }}>
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-sm)' }}>
        <div>
          <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Status</div>
          <span style={{ color: monitoring.status === 'PAPER_TRADING' ? 'var(--green)' : 'var(--text-muted)', fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>{monitoring.status}</span>
        </div>
        <div>
          <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Cycle</div>
          <span style={{ color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>{monitoring.cycle_number || 0}</span>
        </div>
        <div>
          <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Deployment</div>
          <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)', fontFamily: 'var(--font-mono)' }}>{monitoring.deployment_id ? monitoring.deployment_id.substring(0, 8) + '...' : 'N/A'}</span>
        </div>
      </div>
      {monitoring.cpcv_summary && (
        <div style={{ marginTop: 'var(--space-sm)', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-sm)', padding: 'var(--space-sm)', background: 'var(--bg-hover)', borderRadius: 'var(--radius-md)' }}>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>Sharpe</div>
            <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>{(monitoring.cpcv_summary.mean_sharpe || 0).toFixed(2)}</div>
          </div>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>DSR</div>
            <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>{(monitoring.cpcv_summary.dsr || 0).toFixed(2)}</div>
          </div>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>Ann. Return</div>
            <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--green)' }}>{(monitoring.cpcv_summary.annualized_return || 0 * 100).toFixed(1)}%</div>
          </div>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>Win Rate</div>
            <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>{(monitoring.cpcv_summary.win_rate || 0 * 100).toFixed(1)}%</div>
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
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-sm)' }}>
        <div>
          <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Certificate</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)', color: 'var(--green)', marginBottom: 'var(--space-xs)' }}>{certId}</div>
          {issuedAt && (
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-muted)' }}>Issued: {new Date(issuedAt).toLocaleDateString()}</div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', justifyContent: 'center' }}>
          {!exporting ? (
            <button onClick={execExport}
              style={{ padding: 'var(--space-xs) var(--space-md)', borderRadius: 'var(--radius-md)', border: '1px solid var(--green-subtle)', background: 'var(--green-subtle)', color: 'var(--green)', fontSize: 'var(--font-size-sm)', cursor: 'pointer' }}>
              Export Strategy
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              {EXPORT_STEPS.map((s, i) => (
                <div key={s} style={{
                  width: '24px', height: '24px', borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 'var(--font-size-2xs)', fontWeight: 500,
                  background: i < exportStep ? 'var(--green-subtle)' : 'var(--bg-hover)',
                  color: i < exportStep ? 'var(--green)' : 'var(--text-dim)',
                  border: `1px solid ${i < exportStep ? 'var(--green-subtle)' : 'var(--border-input)'}`,
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
      <div style={{ marginBottom: 'var(--space-xs)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '24px', fontWeight: 500, color: 'var(--text-primary)' }}>
          {latestEquity ? `$${parseFloat(latestEquity).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '\u2014'}
        </span>
      </div>
      {latestTime && <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-sm)' }}>{latestTime.toLocaleString()}</div>}

      {/* Period toggle */}
      <div style={{ display: 'flex', gap: 'var(--space-xs)', marginBottom: 'var(--space-sm)' }}>
        {PERIODS.map(({ label, period, tf }) => (
          <button key={label} onClick={() => switchPeriod(period, tf)}
            style={{
              padding: '4px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid',
              borderColor: activePeriod === label ? 'var(--border)' : 'transparent',
              background: activePeriod === label ? 'var(--bg-hover)' : 'transparent',
              color: activePeriod === label ? 'var(--text-primary)' : 'var(--text-dim)',
              fontSize: 'var(--font-size-xs)', cursor: 'pointer', fontWeight: 500,
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
                  <stop offset="0%" stopColor="var(--text-primary)" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="var(--text-primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="time" stroke="var(--text-faint)" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis stroke="var(--text-faint)" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} domain={['dataMin', 'dataMax']} tickFormatter={v => `$${v.toLocaleString()}`} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
              <Area type="monotone" dataKey="equity" stroke="var(--text-primary)" strokeWidth={1.5} fill="url(#portfolioGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)' }}>Loading portfolio data...</div>
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
  const changeColor = dailyChange > 0 ? 'var(--green)' : dailyChange < 0 ? 'var(--red)' : 'var(--text-primary)';

  const col = (label, value, color) => (
    <div>
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>{label}</div>
      <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, color: color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{value}</div>
    </div>
  );

  return (
    <Section title="Balances" lastUpdated={alpaca.lastUpdated} onRefresh={alpaca.fetchAccount}
      action={
        <button onClick={alpaca.fetchAccount}
          style={{ width: '24px', height: '24px', borderRadius: '50%', border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-dim)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--font-size-2xs)', lineHeight: 1 }}>
          &#x21bb;
        </button>
      }>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-sm)' }}>
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

  const headerStyle = { padding: '8px 12px', fontSize: 'var(--font-size-2xs)', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-dim)', fontWeight: 500, textAlign: 'right', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' };
  const headerLeft = { ...headerStyle, textAlign: 'left' };

  return (
    <Section title="Top Positions" lastUpdated={alpaca.lastUpdated} onRefresh={alpaca.fetchPositions}
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <select value={filter} onChange={e => setFilter(e.target.value)}
            style={{ padding: '4px 10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: 'var(--font-size-xs)', outline: 'none' }}>
            <option value="all">All</option>
            <option value="win">Winners</option>
            <option value="loss">Losers</option>
          </select>
          <span style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', cursor: 'pointer' }}>View All</span>
        </div>
      }>
      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-faint)', fontSize: 'var(--font-size-xs)', fontStyle: 'italic' }}>
          No open positions
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-size-sm)' }}>
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
                  <tr key={p.asset_id || p.symbol} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-primary)' }}>{p.symbol}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>${parseFloat(p.current_price).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{parseFloat(p.qty).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>${parseFloat(p.market_value).toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: pl >= 0 ? 'var(--green)' : 'var(--red)' }}>
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
    if (s === 'filled') return { color: 'var(--green)', border: '1px solid var(--green-subtle)', bg: 'var(--green-subtle)' };
    if (s === 'canceled' || s === 'cancelled') return { color: 'var(--red)', border: '1px solid var(--red-subtle)', bg: 'var(--red-subtle)' };
    return { color: 'var(--text-muted)', border: '1px solid var(--border)', bg: 'var(--bg-hover)' };
  };

  const th = { padding: '8px 10px', fontSize: 'var(--font-size-2xs)', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-dim)', fontWeight: 500, textAlign: 'right', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' };
  const thLeft = { ...th, textAlign: 'left' };
  const thCenter = { ...th, textAlign: 'center' };

  return (
    <Section title="Recent Orders" lastUpdated={alpaca.lastUpdated} onRefresh={() => alpaca.fetchOrders()}
      action={
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)', pointerEvents: 'none' }}>&#x1F50D;</span>
            <input placeholder="Search" value={search} onChange={e => setSearch(e.target.value)}
              style={{ padding: '6px 10px 6px 28px', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-xs)', outline: 'none', width: '140px' }} />
          </div>
          {Object.values(selected).some(Boolean) && (
            <button onClick={cancelSelected} disabled={cancelBusy}
              style={{ padding: '4px 10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'transparent', color: 'var(--text-muted)', fontSize: 'var(--font-size-2xs)', cursor: 'pointer' }}>
              Cancel {Object.values(selected).filter(Boolean).length} selected
            </button>
          )}
        </div>
      }>
      {searched.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-faint)', fontSize: 'var(--font-size-xs)', fontStyle: 'italic' }}>
          No orders found
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-size-sm)' }}>
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
                    <tr key={o.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '10px 6px', textAlign: 'center' }}>
                        <input type="checkbox" checked={!!selected[o.id]} onChange={() => toggleSelect(o.id)}
                          style={{ accentColor: 'var(--text-primary)', cursor: 'pointer' }} />
                      </td>
                      <td style={{ padding: '10px 10px', color: 'var(--text-primary)' }}>{o.symbol}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: 'var(--text-muted)' }}>{o.type}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: o.side === 'buy' ? 'var(--green)' : 'var(--red)' }}>{o.side}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{o.qty}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{o.filled_qty || '0'}</td>
                      <td style={{ padding: '10px 10px', textAlign: 'right', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toFixed(2)}` : '\u2014'}</td>
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-xs)', marginTop: 'var(--space-sm)' }}>
            <button onClick={() => setPage(Math.max(0, safePage - 1))} disabled={safePage === 0}
              style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'var(--bg-card)', color: safePage === 0 ? 'var(--text-faint)' : 'var(--text-muted)', cursor: safePage === 0 ? 'default' : 'pointer', fontSize: 'var(--font-size-xs)' }}>
              Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => (
              <button key={i} onClick={() => setPage(i)}
                style={{
                  padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', fontSize: 'var(--font-size-xs)', cursor: 'pointer',
                  background: i === safePage ? 'var(--bg-hover)' : 'var(--bg-card)',
                  color: i === safePage ? 'var(--text-primary)' : 'var(--text-muted)',
                }}>
                {i + 1}
              </button>
            ))}
            <button onClick={() => setPage(Math.min(totalPages - 1, safePage + 1))} disabled={safePage === totalPages - 1}
              style={{ padding: '4px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'var(--bg-card)', color: safePage === totalPages - 1 ? 'var(--text-faint)' : 'var(--text-muted)', cursor: safePage === totalPages - 1 ? 'default' : 'pointer', fontSize: 'var(--font-size-xs)' }}>
              Next
            </button>
          </div>
        </>
      )}
    </Section>
  );
}
