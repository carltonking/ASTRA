import React, { useEffect, useRef, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, ComposedChart } from 'recharts';
import useWebSocket from '../../hooks/useWebSocket';

function SectionTitle({ label }) {
  return <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-lg)' }}>{label}</div>;
}

export default function Backtest({ session }) {
  const chartRef = useRef(null);
  const [tvReady, setTvReady] = useState(false);
  const { lastEvents } = useWebSocket(session?.sessionId);
  const [cpcvData, setCpcvData] = useState(null);
  const [drawdownData, setDrawdownData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(null);

  // TradingView widget
  useEffect(() => {
    if (typeof window !== 'undefined' && !window.TradingView) {
      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = () => setTvReady(true);
      document.head.appendChild(script);
    } else if (window.TradingView) {
      setTvReady(true);
    }
  }, []);

  useEffect(() => {
    if (tvReady && chartRef.current && !chartRef.current._tvWidget) {
      const widget = new window.TradingView.widget({
        container_id: chartRef.current.id || 'tv-chart',
        width: '100%',
        height: 420,
        symbol: 'NASDAQ:AAPL',
        interval: '15',
        timezone: 'Etc/UTC',
        theme: 'Dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0a0a0a',
        enable_publishing: false,
        hide_side_toolbar: false,
        allow_symbol_change: true,
        studies: ['RSI@tv-basicstudies'],
      });
      chartRef.current._tvWidget = widget;
    }
  }, [tvReady]);

    // CPCV data from events + progress tracking
  useEffect(() => {
    const progEvent = lastEvents.find(ev => ev.event === 'pipeline.backtest_progress');
    if (progEvent?.data) {
      setProgress(progEvent.data);
    }
    const event = lastEvents.find(ev => ev.event === 'pipeline.backtest_complete');
    if (event?.data) {
      setProgress(null);
      const d = event.data;
      const cpcv = d.cpcv_summary || {};
      setMetrics({
        meanSharpe: cpcv.mean_sharpe ?? 0,
        dsr: cpcv.dsr ?? 0,
        overfitProb: cpcv.overfitting_probability ?? 0,
        totalReturn: cpcv.annualized_return ?? 0,
        totalTrades: cpcv.n_trades ?? 0,
        leakageVerdict: d.leakage_verdict || 'PENDING',
        reviewVerdict: d.review_board_status || 'PENDING',
      });
      const sharpes = d.sharpe_per_path;
      if (sharpes && sharpes.length) {
        const paths = sharpes.map((s, i) => {
          const len = 100;
          const vals = Array.from({ length: len }, (_, j) => 1 + (s / len) * j);
          return { name: `Path ${i+1}`, values: vals };
        });
        setCpcvData(paths);
        const dd = paths[0].values.map((v, i, a) => i === 0 ? 0 : (v - a[i-1]) / a[i-1]);
        setDrawdownData(dd.map((d, i) => ({ period: i+1, dd: d * 100 })));
      }
      setLoading(false);
    }
  }, [lastEvents]);

  const chartData = cpcvData?.[0]?.values.map((_, i) => {
    const e = { step: i };
    cpcvData.forEach((p, j) => { e[`p${j+1}`] = p.values[i]; });
    return e;
  }) || [];

  const card = { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' };

  return (
    <div>
      <SectionTitle label="Backtest" />

      {/* Real-time progress bar */}
      {progress && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-sm) var(--space-md)', marginBottom: 'var(--space-md)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-xs)' }}>
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-primary)', fontWeight: 500 }}>
              {progress.stage || 'Processing...'}
            </span>
            <span style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)' }}>
              {progress.current ?? 0} / {progress.total ?? 0}
            </span>
          </div>
          <div style={{ width: '100%', height: '4px', background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
            <div style={{
              width: `${progress.total ? ((progress.current || 0) / progress.total) * 100 : 0}%`,
              height: '100%', background: 'var(--text-muted)', borderRadius: 'var(--radius-sm)',
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      )}

      {/* TradingView chart */}
      <div style={card}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Market Overview</div>
        <div
          id="tv-chart"
          ref={chartRef}
          style={{ width: '100%', height: '420px', background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}
        />
        {!tvReady && (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)' }}>
            Loading chart...
          </div>
        )}
      </div>

      {/* CPCV equity curves */}
      <div style={card}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>CPCV Equity Curves</div>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-dim)', fontSize: 'var(--font-size-2xs)' }}>AWAITING DATA</div>
        ) : cpcvData ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
              <XAxis dataKey="step" stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
              <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
              <Legend wrapperStyle={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-muted)' }} />
              {cpcvData.map((_, i) => (
                <Line key={i} type="monotone" dataKey={`p${i+1}`}
                  stroke={['var(--text-muted)', 'var(--text-dim)', 'var(--text-secondary)'][i % 3]} dot={false} strokeWidth={1} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)' }}>No CPCV data yet</div>
        )}
      </div>

      {/* Drawdown */}
      <div style={card}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Drawdown</div>
        {drawdownData ? (
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={drawdownData}>
              <CartesianGrid strokeDasharray="2 2" stroke="var(--border)" />
              <XAxis dataKey="period" stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
              <YAxis stroke="var(--text-faint)" tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-2xs)' }} />
              <Area type="monotone" dataKey="dd" fill="#2a1a1a" stroke="var(--red)" strokeWidth={1} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: 'var(--space-md)', color: 'var(--text-faint)', fontSize: 'var(--font-size-2xs)' }}>No drawdown data</div>
        )}
      </div>

      {/* Metrics */}
      {metrics && (
        <div style={card}>
          <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Metrics</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-sm)', marginBottom: 'var(--space-sm)' }}>
              {[
                ['Mean Sharpe (CPCV)', metrics.meanSharpe?.toFixed(3)],
                ['Deflated Sharpe (DSR)', metrics.dsr?.toFixed(3)],
                ['Overfit Probability', metrics.overfitProb != null ? `${(metrics.overfitProb * 100).toFixed(1)}%` : '\u2014'],
                ['Annualized Return', metrics.totalReturn != null ? `${(metrics.totalReturn * 100).toFixed(1)}%` : '\u2014'],
                ['Total Trades', metrics.totalTrades != null ? metrics.totalTrades : '\u2014'],
              ].map(([k, v]) => (
              <div key={k} style={{ background: 'var(--bg-surface)', padding: 'var(--space-sm)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--text-dim)' }}>
                <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)', fontWeight: 500 }}>{k}</div>
                <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <Pill label={`Leakage: ${metrics.leakageVerdict}`} />
            <Pill label={`Review: ${metrics.reviewVerdict}`} />
          </div>
        </div>
      )}
    </div>
  );
}

function Pill({ label }) {
  return (
    <span style={{
      padding: '3px 12px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)', fontWeight: 500,
      border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent',
    }}>
      {label}
    </span>
  );
}
