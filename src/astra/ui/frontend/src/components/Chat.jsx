import React, { useState } from 'react';

const styles = {
  container: { display: 'flex', flexDirection: 'column', height: '100%' },
  messages: { flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' },
  inputArea: { padding: '12px', borderTop: '1px solid #333', display: 'flex', gap: '8px', background: '#0f0f23' },
  input: { flex: 1, padding: '10px 14px', borderRadius: '8px', border: '1px solid #444',
           background: '#1a1a3e', color: '#e0e0e0', fontSize: '14px', outline: 'none' },
  userBubble: { alignSelf: 'flex-end', background: '#2d4a7a', color: '#fff',
                padding: '10px 14px', borderRadius: '12px 12px 4px 12px', maxWidth: '80%', fontSize: '14px' },
  astraBubble: { alignSelf: 'flex-start', background: '#1e1e3a', color: '#c0c0e0',
                 padding: '10px 14px', borderRadius: '12px 12px 12px 4px', maxWidth: '80%', fontSize: '14px',
                 border: '1px solid #333' },
  sendBtn: { padding: '8px 20px', borderRadius: '8px', border: 'none',
             background: '#3a6ea5', color: '#fff', cursor: 'pointer', fontWeight: 600 },
  loading: { alignSelf: 'flex-start', color: '#888', fontStyle: 'italic', fontSize: '13px' },
  specCard: { background: '#1a2a1a', border: '1px solid #2a5a2a', borderRadius: '8px',
              padding: '12px', marginTop: '8px', fontSize: '13px', color: '#a0d0a0' },
};

export default function Chat({ session }) {
  const [input, setInput] = useState('');
  const msgsEnd = React.useRef(null);

  React.useEffect(() => {
    msgsEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session.messages]);

  const handleSend = async () => {
    if (!input.trim() || session.loading) return;
    const msg = input.trim();
    setInput('');
    if (!session.sessionId) {
      await session.start(msg);
    } else {
      await session.chat(msg);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={styles.container}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #333',
                    background: '#1a1a2e', color: '#e0e0e0', fontWeight: 600 }}>
        ASTRA Chat
      </div>

      <div style={styles.messages}>
        {session.messages.map((msg, i) => (
          <div key={i} style={msg.role === 'user' ? styles.userBubble : styles.astraBubble}>
            {msg.content}
            {msg.role === 'assistant' && session.spec && i === session.messages.length - 1 && (
              <div style={styles.specCard}>
                <strong>Strategy Spec Ready</strong><br />
                Type: {session.spec.strategy_type}<br />
                Symbols: {session.spec.symbols?.join(', ')}<br />
                Hypothesis: {session.spec.market_hypothesis}
              </div>
            )}
          </div>
        ))}
        {session.loading && <div style={styles.loading}>ASTRA is thinking...</div>}
        <div ref={msgsEnd} />
      </div>

      <div style={styles.inputArea}>
        <input
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={session.sessionId ? "Reply to ASTRA..." : "Describe your strategy idea..."}
          disabled={session.loading}
        />
        <button style={styles.sendBtn} onClick={handleSend} disabled={session.loading}>
          Send
        </button>
      </div>
    </div>
  );
}
