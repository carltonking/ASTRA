import { useState, useEffect, useRef } from 'react';

export default function useWebSocket(sessionId) {
  const [events, setEvents] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;

    function connect() {
      const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
      wsRef.current = ws;

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data);
          setEvents(prev => [...prev, event]);
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [sessionId]);

  const lastEvents = events.slice(-10);

  return { events, lastEvents };
}
