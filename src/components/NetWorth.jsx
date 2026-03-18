// MIT License - Copyright (c) 2024 Finance App

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { getNetWorthTrend } from '../utils/csvParser';

const fmt = (v) =>
  '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

export default function NetWorth({ transactions }) {
  const data = getNetWorthTrend(transactions);
  if (data.length === 0) return <div className="tab-content"><p className="empty-state">No data available.</p></div>;

  const latest = data[data.length - 1];
  const bestMonthNet = Math.max(...data.map(d => d.net));
  const avgMonthNet = data.reduce((s, d) => s + d.net, 0) / data.length;

  return (
    <div className="tab-content">
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Current Net Position</span>
          <span className={`stat-value ${latest.netWorth >= 0 ? 'green' : 'red'}`}>
            {fmt(latest.netWorth)}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Best Month Net</span>
          <span className="stat-value green">{fmt(bestMonthNet)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Avg Monthly Net</span>
          <span className={`stat-value ${avgMonthNet >= 0 ? 'green' : 'red'}`}>
            {fmt(avgMonthNet)}
          </span>
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Cumulative Net Worth Trend</h3>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="label" tick={{ fill: '#8b949e', fontSize: 12 }} />
            <YAxis
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
              tick={{ fill: '#8b949e', fontSize: 12 }}
            />
            <Tooltip
              formatter={(value) => [fmt(value), 'Net Worth']}
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px' }}
              labelStyle={{ color: '#e6edf3' }}
            />
            <ReferenceLine y={0} stroke="#484f58" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="netWorth"
              name="Net Worth"
              stroke="#388bfd"
              strokeWidth={2.5}
              dot={{ fill: '#388bfd', r: 4 }}
              activeDot={{ r: 6, fill: '#388bfd' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Monthly Net Income</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="label" tick={{ fill: '#8b949e', fontSize: 12 }} />
            <YAxis
              tickFormatter={v => `$${(v / 1000).toFixed(1)}k`}
              tick={{ fill: '#8b949e', fontSize: 12 }}
            />
            <Tooltip
              formatter={(value) => [fmt(value), 'Monthly Net']}
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px' }}
              labelStyle={{ color: '#e6edf3' }}
            />
            <ReferenceLine y={0} stroke="#484f58" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="net"
              name="Monthly Net"
              stroke="#3fb950"
              strokeWidth={2}
              dot={{ fill: '#3fb950', r: 3 }}
              activeDot={{ r: 5, fill: '#3fb950' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
