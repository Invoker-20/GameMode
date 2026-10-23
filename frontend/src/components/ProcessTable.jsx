import React, { useState, useEffect } from 'react';
import { fetchProcesses } from '../api';

export default function ProcessTable() {
  const [processes, setProcesses] = useState([]);
  const [sortKey, setSortKey] = useState('cpu_percent');
  const [sortAsc, setSortAsc] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadProcesses = async () => {
    try {
      setLoading(true);
      const data = await fetchProcesses();
      if (Array.isArray(data)) {
        setProcesses(data);
      }
    } catch (err) {
      console.error('Failed to load processes:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProcesses();
    const interval = setInterval(loadProcesses, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const sortedProcesses = [...processes].sort((a, b) => {
    const valA = a[sortKey];
    const valB = b[sortKey];
    if (typeof valA === 'string') {
      return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    return sortAsc ? valA - valB : valB - valA;
  });

  return (
    <div className="card">
      <div className="card-title">
        <span>Active Processes (Top 15 by Resource Share)</span>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            type="button"
            className="btn-primary"
            style={{ fontSize: '12px', padding: '4px 10px' }}
            onClick={loadProcesses}
            disabled={loading}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="process-table-container">
        <table className="process-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('pid')}>
                PID {sortKey === 'pid' ? (sortAsc ? '▲' : '▼') : ''}
              </th>
              <th onClick={() => handleSort('name')}>
                Process Name {sortKey === 'name' ? (sortAsc ? '▲' : '▼') : ''}
              </th>
              <th onClick={() => handleSort('cpu_percent')}>
                CPU % {sortKey === 'cpu_percent' ? (sortAsc ? '▲' : '▼') : ''}
              </th>
              <th onClick={() => handleSort('memory_percent')}>
                RAM % {sortKey === 'memory_percent' ? (sortAsc ? '▲' : '▼') : ''}
              </th>
              <th onClick={() => handleSort('nice')}>
                Nice Level {sortKey === 'nice' ? (sortAsc ? '▲' : '▼') : ''}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedProcesses.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                  No processes reported yet.
                </td>
              </tr>
            ) : (
              sortedProcesses.map((proc) => (
                <tr key={proc.pid}>
                  <td>{proc.pid}</td>
                  <td className="process-name-cell">{proc.name}</td>
                  <td style={{ color: proc.cpu_percent > 10 ? 'var(--accent-cyan)' : 'inherit' }}>
                    {proc.cpu_percent.toFixed(1)}%
                  </td>
                  <td>{proc.memory_percent.toFixed(1)}%</td>
                  <td>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: proc.nice > 0 ? 'var(--accent-amber-bg)' : proc.nice < 0 ? 'var(--accent-green-bg)' : 'transparent',
                        color: proc.nice > 0 ? 'var(--accent-amber)' : proc.nice < 0 ? 'var(--accent-green)' : 'inherit',
                      }}
                    >
                      {proc.nice > 0 ? `+${proc.nice}` : proc.nice}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
