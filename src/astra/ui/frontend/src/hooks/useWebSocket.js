import { useState, useEffect, useRef, useCallback } from 'react';

const MAX_EVENTS = 200;
const INITIAL_DELAY = 1000;
const MAX_DELAY = 30000;

function wsUrl(sessionId) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = process.env.NODE_ENV === 'development' ? 'localhost:8000' : window.location.host;
  return `${proto}//${host}/ws/${sessionId}`;
}

export default function useWebSocket(sessionId) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const retryCount = useRef(0);

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current) wsRef.current.close();

    const ws = new WebSocket(wsUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retryCount.current = 0;
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      const delay = Math.min(INITIAL_DELAY * Math.pow(2, retryCount.current), MAX_DELAY);
      retryCount.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        setEvents(prev => {
          const next = [...prev, event];
          return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
        });
      } catch { /* ignore malformed messages */ }
    };
  }, [sessionId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const lastEvents = events.slice(-10);

  return { events, lastEvents, connected };
}
