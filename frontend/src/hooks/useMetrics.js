import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchHistory } from '../api';

const MAX_SAMPLES = 120;

export function useMetrics() {
  const [samples, setSamples] = useState([]);
  const [connected, setConnected] = useState(false);
  const reconnectTimeoutRef = useRef(null);
  const backoffRef = useRef(1000);
  const wsRef = useRef(null);
  const mountedRef = useRef(true);

  // Load existing history buffer once on mount so charts don't start blank
  useEffect(() => {
    let active = true;
    fetchHistory()
      .then((history) => {
        if (active && Array.isArray(history) && history.length > 0) {
          setSamples(history.slice(-MAX_SAMPLES));
        }
      })
      .catch(() => {
        // Fallback: samples will fill via WebSocket
      });
    return () => {
      active = false;
    };
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/metrics`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnected(true);
      backoffRef.current = 1000; // Reset backoff on successful connection
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const sample = JSON.parse(event.data);
        setSamples((prev) => {
          const next = [...prev, sample];
          return next.length > MAX_SAMPLES ? next.slice(-MAX_SAMPLES) : next;
        });
      } catch (err) {
        console.error('Failed to parse incoming WebSocket telemetry:', err);
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      // Exponential backoff reconnect: 1s, 2s, 4s, max 10s
      const delay = backoffRef.current;
      backoffRef.current = Math.min(delay * 2, 10000);
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const latestSample = samples.length > 0 ? samples[samples.length - 1] : null;

  return {
    samples,
    connected,
    latestSample,
  };
}
