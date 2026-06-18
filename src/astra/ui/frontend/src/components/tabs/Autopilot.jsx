import React, { useState, useEffect, useCallback, useRef } from 'react';

/* Autonomous loop control: start/stop the self-improving paper-trading loop
   and watch it trade → measure → optimize → graduate in real time. */

function Section({ title, children, action }) {
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-sm)' }}>
        <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>{label}</div>
      <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, color: color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{value}</div>
    </div>
  );
}

export default function Autopilot({ session, isActive }) {
  const sessionId = session?.session_id || session?.sessionId || null;
  const [status, setStatus] = useState(null);
  const [interval, setIntervalSec] = useState(60);
  const [confirmations, setConfirmations] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const fetchStatus = useCallback(() => {
    if (!sessionId) return;
    fetch(`/api/session/${sessionId}/autopilot/status`)
      .then(r => r.json())
      .then(d => setStatus(d))
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    if (!isActive || !sessionId) return;
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 3000);
    return () => clearInterval(pollRef.current);
  }, [isActive, sessionId, fetchStatus]);

  const start = async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`/api/session/${sessionId}/autopilot/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_seconds: Number(interval), confirmations: Number(confirmations) }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Start failed (${res.status})`);
      }
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true); setError(null);
    try {
      await fetch(`/api/session/${sessionId}/autopilot/stop`, { method: 'POST' });
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!sessionId) {
    return (
      <div style={{ padding: '40px 0' }}>
        <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--space-sm)' }}>Autopilot</div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)' }}>Start a session and build a strategy first.</div>
      </div>
    );
  }

  const running = status?.running;
  const prog = status?.progress || {};
  const graduated = prog.graduated;
  const confirms = prog.graduation_confirmations || confirmations;
  const consec = prog.consecutive_graduations || 0;
  const pct = confirms ? Math.min(100, Math.round((consec / confirms) * 100)) : 0;

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-md)' }}>
        <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--text-primary)' }}>Autopilot</div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
          Autonomous loop: trade paper → measure → self-optimize on degradation → graduate after {confirms} consecutive passing checks. Paper-only; never trades live.
        </div>
      </div>

      {graduated && (
        <div style={{ background: 'var(--green-subtle)', border: '1px solid var(--green-subtle)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-md)', marginBottom: 'var(--space-md)', color: 'var(--green)', fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>
          ✓ Strategy GRADUATED. Export it from the Graduation tab and run it live yourself.
        </div>
      )}

      <Section title="Control" action={
        <span style={{ padding: '2px 10px', borderRadius: 'var(--radius-full)', fontSize: 'var(--font-size-2xs)', fontWeight: 500,
          border: '1px solid ' + (running ? 'var(--green-subtle)' : 'var(--border)'),
          color: running ? 'var(--green)' : 'var(--text-muted)',
          background: running ? 'var(--green-subtle)' : 'transparent' }}>
          {running ? 'RUNNING' : (status?.active ? 'STOPPED' : 'IDLE')}
        </span>
      }>
        <div style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>Tick interval (sec)</div>
            <input type="number" min="1" value={interval} disabled={running}
              onChange={e => setIntervalSec(e.target.value)}
              style={{ width: '110px', padding: '8px 12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)' }} />
          </div>
          <div>
            <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>Consecutive passes to graduate</div>
            <input type="number" min="1" value={confirmations} disabled={running}
              onChange={e => setConfirmations(e.target.value)}
              style={{ width: '110px', padding: '8px 12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-input)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)' }} />
          </div>
          {!running ? (
            <button onClick={start} disabled={busy}
              style={{ padding: 'var(--space-xs) var(--space-lg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--accent)', background: 'var(--accent)', color: '#fff', fontSize: 'var(--font-size-sm)', cursor: busy ? 'default' : 'pointer', fontWeight: 500 }}>
              {busy ? 'Starting…' : 'Start Autopilot'}
            </button>
          ) : (
            <button onClick={stop} disabled={busy}
              style={{ padding: 'var(--space-xs) var(--space-lg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--red-subtle)', background: 'var(--red-subtle)', color: 'var(--red)', fontSize: 'var(--font-size-sm)', cursor: busy ? 'default' : 'pointer', fontWeight: 500 }}>
              {busy ? 'Stopping…' : 'Stop'}
            </button>
          )}
        </div>
        {error && <div style={{ marginTop: 'var(--space-sm)', color: 'var(--red)', fontSize: 'var(--font-size-xs)' }}>{error}</div>}
      </Section>

      {status?.active && (
        <Section title="Progress">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
            <Stat label="Tick" value={prog.tick ?? 0} />
            <Stat label="Gates" value={`${prog.gates_passed ?? 0}/${prog.gates_total ?? 6}`} />
            <Stat label="Sharpe" value={prog.sharpe != null ? Number(prog.sharpe).toFixed(2) : '—'}
              color={prog.sharpe > 0 ? 'var(--green)' : prog.sharpe < 0 ? 'var(--red)' : undefined} />
            <Stat label="Return" value={prog.total_return != null ? `${(prog.total_return * 100).toFixed(2)}%` : '—'}
              color={prog.total_return > 0 ? 'var(--green)' : prog.total_return < 0 ? 'var(--red)' : undefined} />
          </div>

          <div style={{ marginBottom: 'var(--space-sm)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>
              <span>Consecutive passing checks</span>
              <span>{consec}/{confirms}</span>
            </div>
            <div style={{ height: '6px', borderRadius: 'var(--radius-full)', background: 'var(--bg-hover)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: 'var(--green)', transition: 'width 300ms ease' }} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-md)', marginTop: 'var(--space-md)' }}>
            <Stat label="Last action" value={prog.last_action || '—'} />
            <Stat label="Degradation" value={prog.degradation || '—'}
              color={prog.degradation === 'SEVERE' ? 'var(--red)' : prog.degradation === 'ELEVATED' ? 'var(--amber, var(--text-primary))' : undefined} />
            <Stat label="Optimize cycles" value={prog.optimization_cycles ?? 0} />
          </div>

          {status.parameters && Object.keys(status.parameters).length > 0 && (
            <div style={{ marginTop: 'var(--space-md)', padding: 'var(--space-sm)', background: 'var(--bg-hover)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontSize: 'var(--font-size-2xs)', color: 'var(--text-dim)', marginBottom: 'var(--space-xs)' }}>Live parameters</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)', color: 'var(--text-primary)' }}>
                {Object.entries(status.parameters).map(([k, v]) => `${k}=${v}`).join('   ')}
              </div>
            </div>
          )}

          {prog.message && (
            <div style={{ marginTop: 'var(--space-sm)', fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{prog.message}</div>
          )}
          {status.deployment_id && (
            <div style={{ marginTop: 'var(--space-xs)', fontSize: 'var(--font-size-2xs)', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
              deployment {status.deployment_id.substring(0, 8)}… · {status.deployment_status}
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
