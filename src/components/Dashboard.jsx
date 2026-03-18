// MIT License - Copyright (c) 2024 Finance App

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { getMonthlyData, getCategoryTotals } from '../utils/csvParser';

const fmt = (v) =>
  '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const CATEGORY_COLORS = {
  discretionary: '#63b3ed',
  groceries: '#f6e05e',
  dining: '#f6ad55',
  subscriptions: '#b794f4',
  utilities: '#76e4f7',
  debt: '#fc8181',
  transfer: '#a0aec0',
};

export default function Dashboard({ transactions }) {
  const monthly = getMonthlyData(transactions);
  const categories = getCategoryTotals(transactions);
  const totalIncome = transactions
    .filter(t => t.isCredit)
    .reduce((s, t) => s + t.amount, 0);
  const totalSpending = transactions
    .filter(t => !t.isCredit)
    .reduce((s, t) => s + Math.abs(t.amount), 0);
  const netSavings = totalIncome - totalSpending;
  const savingsRate = totalIncome > 0 ? ((netSavings / totalIncome) * 100).toFixed(1) : '0.0';

  return (
    <div className="tab-content">
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Total Income</span>
          <span className="stat-value green">{fmt(totalIncome)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Spending</span>
          <span className="stat-value red">{fmt(totalSpending)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Net Savings</span>
          <span className={`stat-value ${netSavings >= 0 ? 'green' : 'red'}`}>{fmt(netSavings)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Savings Rate</span>
          <span className={`stat-value ${parseFloat(savingsRate) >= 20 ? 'green' : 'yellow'}`}>{savingsRate}%</span>
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Monthly Income vs Spending</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={monthly} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis dataKey="label" tick={{ fill: '#8b949e', fontSize: 12 }} />
            <YAxis
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
              tick={{ fill: '#8b949e', fontSize: 12 }}
            />
            <Tooltip
              formatter={(value, name) => [fmt(value), name]}
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px' }}
              labelStyle={{ color: '#e6edf3' }}
            />
            <Legend wrapperStyle={{ color: '#8b949e', fontSize: 13 }} />
            <Bar dataKey="income" name="Income" fill="#3fb950" radius={[4, 4, 0, 0]} />
            <Bar dataKey="spending" name="Spending" fill="#f85149" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Spending by Category</h3>
        <div className="category-list">
          {categories.map(({ category, total }) => {
            const pct = totalSpending > 0 ? (total / totalSpending) * 100 : 0;
            const color = CATEGORY_COLORS[category] || '#8b949e';
            return (
              <div key={category} className="category-row">
                <span className="category-name">{category}</span>
                <div className="category-bar-track">
                  <div
                    className="category-bar-fill"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
                <span className="category-amount">
                  {fmt(total)} <span className="category-pct">({pct.toFixed(1)}%)</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
