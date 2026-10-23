import React, { useState } from 'react';
import { toggleMode } from '../api';

export default function ModeToggle({ status, onStatusChange }) {
  const [loading, setLoading] = useState(false);
  const [actionResults, setActionResults] = useState(null);
  const [error, setError] = useState(null);

  const modeEnabled = status?.mode_enabled ?? false;
  const capabilities = status?.capabilities || {};
  const actions = status?.actions || [];

  const handleToggle = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await toggleMode(!modeEnabled);
      setActionResults(resp.results || []);
      if (onStatusChange) {
        onStatusChange();
      }
    } catch (err) {
      setError(err.message || 'Failed to toggle GameMode');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card mode-toggle-card">
      <div className="card-title">
        <span>Optimizer Controls</span>
        {capabilities.dry_run && (
          <span className="cap-badge ok" style={{ background: 'rgba(56, 189, 248, 0.15)', color: 'var(--accent-cyan)' }}>
            DRY RUN MODE
          </span>
        )}
      </div>

      <div className="main-toggle-wrapper">
        <button
          type="button"
          className={`toggle-button ${modeEnabled ? 'active' : 'inactive'}`}
          onClick={handleToggle}
          disabled={loading}
        >
          {loading ? (
            'Processing Request...'
          ) : modeEnabled ? (
            <>
              <span>⚡</span> GameMode ACTIVE (Click to Disable)
            </>
          ) : (
            <>
              <span>🎮</span> Enable GameMode Optimizations
            </>
          )}
        </button>

        {error && (
          <div style={{ color: 'var(--accent-red)', fontSize: '13px', textAlign: 'center' }}>
            {error}
          </div>
        )}
      </div>

      <div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 600 }}>
          KERNEL & HARDWARE CAPABILITIES
        </div>
        <div className="capabilities-grid">
          <div className="capability-pill">
            <span>PSI (/proc/pressure)</span>
            <span className={`cap-badge ${capabilities.psi ? 'ok' : 'no'}`}>
              {capabilities.psi ? 'YES' : 'NO'}
            </span>
          </div>
          <div className="capability-pill">
            <span>CPUFreq Sysfs</span>
            <span className={`cap-badge ${capabilities.cpufreq ? 'ok' : 'no'}`}>
              {capabilities.cpufreq ? 'YES' : 'NO'}
            </span>
          </div>
          <div className="capability-pill">
            <span>Governor Tuning</span>
            <span className={`cap-badge ${capabilities.governor_writable ? 'ok' : 'no'}`}>
              {capabilities.governor_writable ? 'WRITABLE' : 'LOCKED'}
            </span>
          </div>
          <div className="capability-pill">
            <span>Process Renicing</span>
            <span className={`cap-badge ${capabilities.can_renice ? 'ok' : 'no'}`}>
              {capabilities.can_renice ? 'PERMITTED' : 'RESTRICTED'}
            </span>
          </div>
          <div className="capability-pill">
            <span>VM Swappiness</span>
            <span className={`cap-badge ${capabilities.swappiness_writable ? 'ok' : 'no'}`}>
              {capabilities.swappiness_writable ? 'WRITABLE' : 'LOCKED'}
            </span>
          </div>
          <div className="capability-pill">
            <span>Root Privileges</span>
            <span className={`cap-badge ${capabilities.is_root ? 'ok' : 'no'}`}>
              {capabilities.is_root ? 'ROOT (0)' : 'USER'}
            </span>
          </div>
        </div>
      </div>

      <div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 600 }}>
          OPTIMIZATION ACTIONS (WRITE-AHEAD REVERSIBLE)
        </div>
        <div className="actions-list">
          {actions.map((act) => {
            const stateClass = `tag-${act.state}`;
            return (
              <div key={act.name} className="action-row">
                <div className="action-header">
                  <span className="action-name">{act.name}</span>
                  <span className={`action-status-tag ${stateClass}`}>
                    {act.state.replace('_', ' ')}
                  </span>
                </div>
                <div className="action-reason">{act.reason}</div>
              </div>
            );
          })}
        </div>
      </div>

      {actionResults && actionResults.length > 0 && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 600 }}>
            LATEST EXECUTION LOG
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {actionResults.map((res) => (
              <div
                key={res.action}
                style={{
                  fontSize: '12px',
                  fontFamily: 'var(--font-mono)',
                  color: res.status === 'applied' || res.status === 'reverted' ? 'var(--accent-green)' : 'var(--accent-amber)',
                }}
              >
                [{res.status.toUpperCase()}] {res.action}: {res.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
