import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

export default function Chat({ session }) {
  const [input, setInput] = useState('');
  const msgsEnd = useRef(null);
  const [hoveredChip, setHoveredChip] = useState(null);
  const { sessionId, messages, loading, start, chat } = session;
  const timesRef = useRef([]);

  useEffect(() => {
    msgsEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    const t = timesRef.current;
    while (t.length < messages.length) t.push(new Date());
  }, [messages]);

  const send = async (msg) => {
    const m = msg || input.trim();
    if (!m) return;
    setInput('');
    if (!sessionId) await start(m);
    else await chat(m);
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const fmt = (d) => d instanceof Date ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  const chips = !sessionId
    ? ['Momentum on SPY', 'Mean reversion on QQQ', 'Trend following on AAPL', 'Pairs: GOOGL/MSFT']
    : ['Use daily data', 'Lower risk threshold', 'Show what you have', 'Run with defaults'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Scrollable messages */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '16px',
        display: 'flex', flexDirection: 'column', gap: '12px',
      }}>
        {messages.length === 0 && !loading && (
          <div style={{
            alignSelf: 'center', textAlign: 'center', marginTop: '60px',
            color: '#555', fontSize: '12px', lineHeight: 2,
          }}>
            Describe a trading idea<br />
            <span style={{ color: '#444', fontSize: '11px' }}>
              e.g. &ldquo;Momentum on SPY with 50-day SMA filter&rdquo;
            </span>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '88%',
          }}>
            <div style={{
              padding: '8px 12px',
              borderRadius: msg.role === 'user' ? '8px 8px 4px 8px' : '8px 8px 8px 4px',
              background: msg.role === 'user' ? '#1a1a1a' : 'transparent',
              border: msg.role === 'user' ? '1px solid #2a2a2a' : 'none',
              fontSize: '12px', lineHeight: 1.6, color: '#e8e8e8',
            }}>
              {msg.role === 'user' ? (
                <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
              ) : (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              )}
            </div>
            <div style={{
              fontSize: '10px', color: '#444', marginTop: '4px',
              textAlign: msg.role === 'user' ? 'right' : 'left', padding: '0 4px',
            }}>
              {fmt(timesRef.current[i])}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: 'flex-start', color: '#666', fontSize: '11px', fontStyle: 'italic' }}>
            thinking...
          </div>
        )}
        <div ref={msgsEnd} />
      </div>

      {/* Chips */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: '6px',
        padding: '0 16px 10px', background: '#0a0a0a',
      }}>
        {chips.map((c, i) => (
          <button key={i} onClick={() => send(c)} disabled={loading}
            onMouseEnter={() => setHoveredChip(i)}
            onMouseLeave={() => setHoveredChip(null)}
            style={{
              background: hoveredChip === i ? '#1a1a1a' : 'transparent',
              border: '1px solid #2a2a2a', borderRadius: '9999px',
              padding: '4px 12px', fontSize: '11px', color: '#777',
              cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.4 : 1,
            }}>
            {c}
          </button>
        ))}
      </div>

      {/* Input + Send */}
      <div style={{
        padding: '0 16px 12px', display: 'flex', gap: '8px',
        background: '#0a0a0a',
      }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={sessionId ? 'Reply to ASTRA...' : 'Describe your strategy...'}
          disabled={loading}
          style={{
            flex: 1, padding: '9px 14px', borderRadius: '8px',
            border: '1px solid #2a2a2a', background: '#161616',
            color: '#e8e8e8', fontSize: '13px', outline: 'none',
          }}
        />
        <button onClick={() => send()} disabled={loading}
          style={{
            padding: '9px 18px', borderRadius: '6px', border: 'none',
            background: '#252525', color: '#e8e8e8', fontSize: '13px',
            fontWeight: 500, cursor: loading ? 'default' : 'pointer',
            opacity: loading ? 0.4 : 1,
          }}>
          Send
        </button>
      </div>

      {/* Footer */}
      <div style={{
        height: '28px', minHeight: '28px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '10px', color: '#3a3a3a',
        borderTop: '1px solid #1e1e1e', background: '#0a0a0a',
      }}>
        RESEARCH PURPOSES ONLY — Not financial advice
      </div>
    </div>
  );
}
