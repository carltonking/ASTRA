import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'react-toastify';

const API = axios.create({ baseURL: process.env.NODE_ENV === 'development' ? 'http://localhost:8000/api' : '/api' });

export default function useSession() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('astra_session_id') || null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [spec, setSpec] = useState(null);
  const [isComplete, setIsComplete] = useState(false);
  const [sessionState, setSessionState] = useState(null);

  const fetchState = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await API.get(`/session/${sessionId}/state`);
      setSessionState(res.data);
    } catch (err) {
      console.warn('Failed to fetch state', err);
    }
  }, [sessionId]);

  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('astra_session_id', sessionId);
      fetchState();
    }
  }, [sessionId, fetchState]);

  const start = useCallback(async (userIdea) => {
    setLoading(true);
    try {
      const res = await API.post('/session/start', { user_idea: userIdea });
      const data = res.data;
      setSessionId(data.session_id);
      setMessages([{ role: 'assistant', content: data.message }]);
      toast.success('Session started!');
      return data;
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      toast.error(`Failed to start: ${msg}`);
      setMessages([{ role: 'assistant', content: `Error: ${msg}` }]);
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
      const msg = err.response?.data?.detail || err.message;
      toast.error(`Chat error: ${msg}`);
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${msg}` }]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const doExport = useCallback(async () => {
    if (!sessionId) return null;
    try {
      const res = await API.post(`/session/${sessionId}/export`);
      toast.success('Export package generated!');
      return res.data;
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      toast.error(`Export failed: ${msg}`);
      return null;
    }
  }, [sessionId]);

  const newSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setSpec(null);
    setIsComplete(false);
    setSessionState(null);
    localStorage.removeItem('astra_session_id');
  }, []);

  return {
    sessionId, messages, loading, spec, isComplete, sessionState,
    start, chat, fetchState, doExport, newSession,
  };
}
