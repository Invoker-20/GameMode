import React, { useState, useEffect, useRef } from 'react';
import {
  startBenchmark,
  fetchBenchmarks,
  fetchBenchmark,
  compareBenchmarks,
} from '../api';

export default function BenchmarkPanel() {
  const [benchmarks, setBenchmarks] = useState([]);
  const [label, setLabel] = useState('Benchmark Run');
  const [repetitions, setRepetitions] = useState(3);
  const [syntheticContention, setSyntheticContention] = useState(false);
  const [runningBenchId, setRunningBenchId] = useState(null);
  const [pollError, setPollError] = useState(null);

  // Comparison selection
  const [runAId, setRunAId] = useState('');
  const [runBId, setRunBId] = useState('');
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);

  const pollIntervalRef = useRef(null);

  const loadBenchmarkList = async () => {
    try {
      const list = await fetchBenchmarks();
      if (Array.isArray(list)) {
        setBenchmarks(list);
        if (list.length >= 2 && !runAId && !runBId) {
          setRunAId(String(list[1].id));
          setRunBId(String(list[0].id));
        } else if (list.length >= 1 && !runAId) {
          setRunAId(String(list[0].id));
        }
      }
    } catch (err) {
      console.error('Error fetching benchmarks:', err);
    }
  };

  useEffect(() => {
    loadBenchmarkList();
  }, []);

  // Poll for currently running benchmark completion
  useEffect(() => {
    if (!runningBenchId) return;

    pollIntervalRef.current = setInterval(async () => {
      try {
        const item = await fetchBenchmark(runningBenchId);
        if (item && item.results !== null) {
          clearInterval(pollIntervalRef.current);
          setRunningBenchId(null);
          await loadBenchmarkList();
          setRunBId(String(item.id));
        }
      } catch (err) {
        setPollError('Failed polling benchmark status');
      }
    }, 1500);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [runningBenchId]);

  const handleStart = async (e) => {
    e.preventDefault();
    setPollError(null);
    try {
      const resp = await startBenchmark({
        label: label.trim() || 'Benchmark Run',
        repetitions: Number(repetitions),
        synthetic_contention: syntheticContention,
      });
      setRunningBenchId(resp.id);
    } catch (err) {
      setPollError(err.message || 'Failed starting benchmark');
    }
  };

  // Compare selected runs
  useEffect(() => {
    if (!runAId || !runBId || runAId === runBId) {
      setComparisonData(null);
      return;
    }

    let active = true;
    setComparing(true);
    compareBenchmarks(runAId, runBId)
      .then((data) => {
        if (active) {
          setComparisonData(data);
        }
      })
      .catch((err) => {
        console.error('Comparison error:', err);
      })
      .finally(() => {
        if (active) setComparing(false);
      });

    return () => {
      active = false;
    };
  }, [runAId, runBId]);

  return (
    <div className="card benchmark-layout">
      <div className="card-title">
        <span>Performance Benchmark Suite</span>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 400 }}>
          OS Scheduling Latency, CPU Workload & Disk I/O
        </span>
      </div>

      <div className="benchmark-disclaimer">
        <span>⚖️</span>
        <span>
          <strong>Strict Telemetry Rule:</strong> System-level metrics only; this does not measure FPS.
          Differences within measurement spread are marked &quot;no significant change&quot;.
        </span>
      </div>

      {/* Benchmark Execution Form */}
      <form onSubmit={handleStart} className="benchmark-controls">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Run Label</label>
          <input
            type="text"
            className="input-field"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={Boolean(runningBenchId)}
            placeholder="e.g. Mode On - Contention"
            style={{ width: '220px' }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Repetitions</label>
          <select
            className="input-field"
            value={repetitions}
            onChange={(e) => setRepetitions(e.target.value)}
            disabled={Boolean(runningBenchId)}
          >
            <option value={2}>2 (Quick - ~5s)</option>
            <option value={3}>3 (Standard - ~8s)</option>
            <option value={5}>5 (High Precision - ~15s)</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '18px' }}>
          <input
            type="checkbox"
            id="contention"
            checked={syntheticContention}
            onChange={(e) => setSyntheticContention(e.target.checked)}
            disabled={Boolean(runningBenchId)}
          />
          <label htmlFor="contention" style={{ fontSize: '13px', cursor: 'pointer' }}>
            Synthetic CPU Contention (Simulate background load)
          </label>
        </div>

        <button
          type="submit"
          className="btn-primary"
          style={{ marginTop: '18px' }}
          disabled={Boolean(runningBenchId)}
        >
          {runningBenchId ? `Running Benchmark #${runningBenchId}...` : 'Start Benchmark'}
        </button>
      </form>

      {pollError && (
        <div style={{ color: 'var(--accent-red)', fontSize: '13px' }}>
          {pollError}
        </div>
      )}

      {/* Comparison Section */}
      <div className="comparison-card">
        <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff' }}>
          Statistical Differential Comparison
        </div>

        <div className="comparison-selectors">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Baseline (A):</span>
            <select
              className="input-field"
              value={runAId}
              onChange={(e) => setRunAId(e.target.value)}
            >
              <option value="">Select Run</option>
              {benchmarks.map((b) => (
                <option key={b.id} value={b.id}>
                  #{b.id} — {b.label} ({b.mode_enabled ? 'GameMode ON' : 'GameMode OFF'})
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Comparison (B):</span>
            <select
              className="input-field"
              value={runBId}
              onChange={(e) => setRunBId(e.target.value)}
            >
              <option value="">Select Run</option>
              {benchmarks.map((b) => (
                <option key={b.id} value={b.id}>
                  #{b.id} — {b.label} ({b.mode_enabled ? 'GameMode ON' : 'GameMode OFF'})
                </option>
              ))}
            </select>
          </div>
        </div>

        {comparing && (
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Computing statistical delta...
          </div>
        )}

        {comparisonData && comparisonData.metrics_comparison ? (
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Benchmark Metric</th>
                <th>Baseline Median (A)</th>
                <th>Run B Median</th>
                <th>Spread (Noise Margin)</th>
                <th>Statistical Delta</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(comparisonData.metrics_comparison).map(([metricKey, data]) => {
                const metricLabels = {
                  scheduling_latency_p50_us: 'Scheduling Latency p50 (μs)',
                  scheduling_latency_p95_us: 'Scheduling Latency p95 (μs)',
                  scheduling_latency_p99_us: 'Scheduling Latency p99 (μs)',
                  scheduling_latency_max_us: 'Scheduling Latency Max (μs)',
                  cpu_computation_elapsed_s: 'CPU Computation Workload (s)',
                  disk_write_mb_s: 'Sequential Disk Write (MB/s)',
                  disk_read_mb_s: 'Sequential Disk Read (MB/s)',
                };

                const isLatencyOrElapsed = metricKey.includes('latency') || metricKey.includes('elapsed');
                const isPositiveGood = !isLatencyOrElapsed;
                let badgeClass = 'neutral';

                if (data.significant) {
                  if (data.percent_change < 0) {
                    badgeClass = isLatencyOrElapsed ? 'better' : 'worse';
                  } else if (data.percent_change > 0) {
                    badgeClass = isPositiveGood ? 'better' : 'worse';
                  }
                }

                return (
                  <tr key={metricKey}>
                    <td style={{ fontWeight: 500, color: '#fff' }}>
                      {metricLabels[metricKey] || metricKey}
                    </td>
                    <td>{data.median_a}</td>
                    <td>{data.median_b}</td>
                    <td style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      ±{Math.max(data.spread_a, data.spread_b)}
                    </td>
                    <td>
                      <span className={`delta-badge ${badgeClass}`}>
                        {data.summary}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '12px 0' }}>
            {benchmarks.length < 2
              ? 'Run at least two benchmarks (e.g., one with GameMode OFF, one with GameMode ON) to generate differential comparison.'
              : 'Select two different runs above to view comparison.'}
          </div>
        )}
      </div>
    </div>
  );
}
