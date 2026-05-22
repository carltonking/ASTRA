import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = '/api/broker';

export default function useAlpaca({ enabled = true } = {}) {
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [portfolioHistory, setPortfolioHistory] = useState(null);
  const [prices, setPrices] = useState({});
  const [wsConnected, setWsConnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [configured, setConfigured] = useState(false);
  const prevPricesRef = useRef({});
  const pendingRef = useRef({});

  useEffect(() => {
    fetch(`${API_BASE}/status`)
      .then(r => r.json())
      .then(d => setConfigured(d.configured))
      .catch(() => setConfigured(false));
  }, []);

  const withDedup = (key, fn) => async (...args) => {
    if (pendingRef.current[key]) return;
    pendingRef.current[key] = true;
    try { return await fn(...args); }
    finally { pendingRef.current[key] = false; }
  };

  const fetchAccount = useCallback(withDedup('account', async () => {
    try {
      const res = await fetch(`${API_BASE}/account`);
      if (!res.ok) throw new Error(`Proxy ${res.status}`);
      const data = await res.json();
      setAccount(data);
      return data;
    } catch (e) { console.warn('Account fetch failed:', e.message); return null; }
  }), []);

  const fetchPositions = useCallback(withDedup('positions', async () => {
    try {
      const res = await fetch(`${API_BASE}/positions`);
      if (!res.ok) throw new Error(`Proxy ${res.status}`);
      const data = await res.json();
      setPositions(data);
      return data;
    } catch (e) { console.warn('Positions fetch failed:', e.message); return []; }
  }), []);

  const fetchOrders = useCallback(withDedup('orders', async (status = 'all', limit = 50) => {
    try {
      const res = await fetch(`${API_BASE}/orders?status=${status}&limit=${limit}`);
      if (!res.ok) throw new Error(`Proxy ${res.status}`);
      const data = await res.json();
      setOrders(data);
      return data;
    } catch (e) { console.warn('Orders fetch failed:', e.message); return []; }
  }), []);

  const cancelOrder = useCallback(async (orderId) => {
    const res = await fetch(`${API_BASE}/orders/${orderId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`Cancel failed ${res.status}`);
    await fetchOrders();
  }, [fetchOrders]);

  const placeOrder = useCallback(async ({ symbol, qty, side, type, timeInForce }) => {
    const params = new URLSearchParams({
      symbol: symbol.toUpperCase(), qty: String(qty), side,
      order_type: type || 'market', time_in_force: timeInForce || 'day',
    });
    const res = await fetch(`${API_BASE}/orders?${params}`, { method: 'POST' });
    if (!res.ok) { const e = await res.text(); throw new Error(e); }
    await fetchOrders();
    return res.json();
  }, [fetchOrders]);

  const fetchPortfolioHistory = useCallback(withDedup('portfolio', async (period = '1M', timeframe = '1D') => {
    try {
      const res = await fetch(`${API_BASE}/portfolio?period=${period}&timeframe=${timeframe}`);
      if (!res.ok) throw new Error(`Proxy ${res.status}`);
      const data = await res.json();
      setPortfolioHistory(data);
      return data;
    } catch (e) { console.warn('Portfolio fetch failed:', e.message); return null; }
  }), []);

  const refreshTimer = useRef(null);
  const refreshAll = useCallback(() => {
    if (!configured) return;
    fetchAccount();
    fetchPositions();
    fetchOrders();
    setLastUpdated(new Date());
  }, [configured, fetchAccount, fetchPositions, fetchOrders]);

  useEffect(() => {
    if (!configured || !enabled) return;
    refreshAll();
    refreshTimer.current = setInterval(refreshAll, 30000);
    return () => clearInterval(refreshTimer.current);
  }, [configured, enabled, refreshAll]);

  // WebSocket for live prices (direct to Alpaca — read-only)
  useEffect(() => {
    setPrices({});
    setWsConnected(false);
    return () => {};
  }, [configured, enabled]);

  return {
    configured,
    account, fetchAccount,
    positions, fetchPositions,
    orders, fetchOrders,
    cancelOrder, placeOrder,
    portfolioHistory, fetchPortfolioHistory,
    prices, wsConnected, lastUpdated,
  };
}
