import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export default function MetricsCharts({ samples, latestSample }) {
  // Format sample series for Recharts
  const chartData = useMemo(() => {
    return samples.map((s, idx) => {
      const timeStr = s.timestamp ? s.timestamp.substring(11, 19) : `${idx}s`;
      const diskReadMB = s.disk ? +(s.disk.read_bytes_per_s / (1024 * 1024)).toFixed(2) : 0;
      const diskWriteMB = s.disk ? +(s.disk.write_bytes_per_s / (1024 * 1024)).toFixed(2) : 0;

      // Extract PSI some avg10 values if available
      const psiCpuAvg10 = s.psi?.cpu?.some?.avg10 ?? null;
      const psiMemAvg10 = s.psi?.memory?.some?.avg10 ?? null;
      const psiIoAvg10 = s.psi?.io?.some?.avg10 ?? null;

      return {
        time: timeStr,
        cpuPercent: s.cpu?.total_percent ?? 0,
        memPercent: s.memory?.percent ?? 0,
        swapPercent: s.memory?.swap_percent ?? 0,
        diskReadMB,
        diskWriteMB,
        psiCpu: psiCpuAvg10,
        psiMem: psiMemAvg10,
        psiIo: psiIoAvg10,
      };
    });
  }, [samples]);

  const hasPsi = latestSample?.psi?.cpu !== null || latestSample?.psi?.memory !== null;

  const currentCpu = latestSample?.cpu?.total_percent ?? 0;
  const currentMem = latestSample?.memory?.percent ?? 0;
  const currentDiskR = latestSample?.disk ? (latestSample.disk.read_bytes_per_s / (1024 * 1024)).toFixed(1) : '0.0';
  const currentDiskW = latestSample?.disk ? (latestSample.disk.write_bytes_per_s / (1024 * 1024)).toFixed(1) : '0.0';

  return (
    <div className="card">
      <div className="card-title">
        <span>Live System Telemetry</span>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 400 }}>
          Streaming at 1 Hz (120s buffer)
        </span>
      </div>

      <div className="charts-grid">
        {/* Chart 1: CPU Utilization */}
        <div className="chart-card">
          <div className="chart-header">
            <span>CPU Utilization</span>
            <span className="chart-metric-value">{currentCpu}%</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#273042" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke="#6e7681" tick={{ fontSize: 10 }} />
                <YAxis stroke="#6e7681" domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#181d28', borderColor: '#273042', borderRadius: '6px' }}
                />
                <Line
                  type="monotone"
                  dataKey="cpuPercent"
                  name="CPU Total"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Memory & Swap */}
        <div className="chart-card">
          <div className="chart-header">
            <span>Memory & Swap Allocation</span>
            <span className="chart-metric-value">{currentMem}% RAM</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#273042" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke="#6e7681" tick={{ fontSize: 10 }} />
                <YAxis stroke="#6e7681" domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#181d28', borderColor: '#273042', borderRadius: '6px' }}
                />
                <Legend wrapperStyle={{ fontSize: 11, bottom: 0 }} />
                <Line
                  type="monotone"
                  dataKey="memPercent"
                  name="RAM %"
                  stroke="#bc8cff"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="swapPercent"
                  name="Swap %"
                  stroke="#d29922"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 3: Disk I/O Throughput */}
        <div className="chart-card">
          <div className="chart-header">
            <span>Disk I/O Throughput</span>
            <span className="chart-metric-value">
              R: {currentDiskR} MB/s | W: {currentDiskW} MB/s
            </span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="#273042" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke="#6e7681" tick={{ fontSize: 10 }} />
                <YAxis stroke="#6e7681" tick={{ fontSize: 10 }} unit="MB" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#181d28', borderColor: '#273042', borderRadius: '6px' }}
                />
                <Legend wrapperStyle={{ fontSize: 11, bottom: 0 }} />
                <Line
                  type="monotone"
                  dataKey="diskReadMB"
                  name="Read MB/s"
                  stroke="#3fb950"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="diskWriteMB"
                  name="Write MB/s"
                  stroke="#f85149"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 4: Linux Pressure Stall Information (PSI) */}
        <div className="chart-card">
          <div className="chart-header">
            <span>Resource Pressure (PSI some avg10)</span>
            {hasPsi && (
              <span className="chart-metric-value" style={{ color: 'var(--accent-amber)' }}>
                Contention %
              </span>
            )}
          </div>

          {!hasPsi ? (
            <div className="psi-unsupported-banner">
              <span style={{ fontSize: '24px' }}>ℹ️</span>
              <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                Pressure Stall Information (PSI) not available
              </span>
              <span style={{ maxWidth: '380px' }}>
                Requires Linux kernel 4.20+ with CONFIG_PSI=y enabled in /proc/pressure.
                (Unavailable on non-Linux or without PSI kernel support).
              </span>
            </div>
          ) : (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="#273042" strokeDasharray="3 3" />
                  <XAxis dataKey="time" stroke="#6e7681" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#6e7681" tick={{ fontSize: 10 }} unit="%" domain={[0, 'auto']} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#181d28', borderColor: '#273042', borderRadius: '6px' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, bottom: 0 }} />
                  <Line
                    type="monotone"
                    dataKey="psiCpu"
                    name="CPU Stall %"
                    stroke="#58a6ff"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="psiMem"
                    name="Memory Stall %"
                    stroke="#d29922"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="psiIo"
                    name="I/O Stall %"
                    stroke="#f85149"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
