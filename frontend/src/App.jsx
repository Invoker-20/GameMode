import React, { useState, useEffect, useCallback } from 'react';
import { useMetrics } from './hooks/useMetrics';
import { fetchStatus } from './api';
import ModeToggle from './components/ModeToggle';
import MetricsCharts from './components/MetricsCharts';
import ProcessTable from './components/ProcessTable';
import BenchmarkPanel from './components/BenchmarkPanel';
import './styles.css';

export default function App() {
  const { samples, connected, latestSample } = useMetrics();
  const [status, setStatus] = useState(null);

  const refreshStatus = useCallback(async () => {
    try {
      const data = await fetchStatus();
      setStatus(data);
    } catch (err) {
      console.error('Failed to fetch status:', err);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    // Poll status periodically (e.g. every 5 seconds) to keep capabilities in sync
    const interval = setInterval(refreshStatus, 5000);
    return () => clearInterval(interval);
  }, [refreshStatus]);

  const modeEnabled = status?.mode_enabled ?? false;

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-icon">🎮</div>
          <div>
            <h1 className="brand-title">GameMode Lab</h1>
            <p className="brand-subtitle">
              Linux Gaming Performance Optimizer, Write-Ahead Reversible Tuning & Telemetry
            </p>
          </div>
        </div>

        <div className="header-status">
          <div className="connection-badge">
            <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
            <span>{connected ? 'WS LIVE (1Hz)' : 'RECONNECTING...'}</span>
          </div>

          <div
            style={{
              padding: '6px 14px',
              borderRadius: '20px',
              fontWeight: 700,
              fontSize: '12px',
              letterSpacing: '0.5px',
              background: modeEnabled ? 'var(--accent-green-bg)' : 'rgba(139, 148, 158, 0.15)',
              color: modeEnabled ? 'var(--accent-green)' : 'var(--text-secondary)',
              border: `1px solid ${modeEnabled ? 'rgba(63, 185, 80, 0.4)' : 'var(--border-color)'}`,
            }}
          >
            {modeEnabled ? 'GAMEMODE ACTIVE' : 'GAMEMODE INACTIVE'}
          </div>
        </div>
      </header>

      {/* Main Grid: Controls + Live Charts */}
      <div className="dashboard-grid">
        <ModeToggle status={status} onStatusChange={refreshStatus} />
        <MetricsCharts samples={samples} latestSample={latestSample} />
      </div>

      {/* Top Processes Table */}
      <ProcessTable />

      {/* Performance Benchmark Suite & Statistical Comparison */}
      <BenchmarkPanel />
    </div>
  );
}
