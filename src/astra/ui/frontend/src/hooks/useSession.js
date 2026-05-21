import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API = axios.create({ baseURL: 'http://localhost:8000/api' });

export default function useSession() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('astra_session_id') || null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [spec, setSpec] = useState(null);
  const [isComplete, setIsComplete] = useState(false);
  const [sessionState, setSessionState] = useState(null);

  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('astra_session_id', sessionId);
      fetchState();
    }
  }, [sessionId]);

  const start = useCallback(async (userIdea) => {
    setLoading(true);
    try {
      const res = await API.post('/session/start', { user_idea: userIdea });
      const data = res.data;
      setSessionId(data.session_id);
      setMessages([{ role: 'assistant', content: data.message }]);
      return data;
    } catch (err) {
      setMessages([{ role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }, []);

  const chat = useCallback(async (message) => {
    if (!sessionId) return;
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    try {
      const res = await API.post(`/session/${sessionId}/chat`, { message });
      const data = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: data.message }]);
      setIsComplete(data.is_complete);
      if (data.spec) setSpec(data.spec);
      return data;
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const fetchState = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await API.get(`/session/${sessionId}/state`);
      setSessionState(res.data);
    } catch { /* silent */ }
  }, [sessionId]);

  const doExport = useCallback(async () => {
    if (!sessionId) return null;
    try {
      const res = await API.post(`/session/${sessionId}/export`);
      return res.data;
    } catch {
      return null;
    }
  }, [sessionId]);

  return { sessionId, messages, setMessages, loading, setLoading, spec, isComplete,
           sessionState, start, chat, fetchState, doExport };
}
