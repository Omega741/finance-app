// MIT License - Copyright (c) 2024 Finance App

import { CATEGORY_OPTIONS } from '../utils/csvParser';

const fmt = (v) =>
  '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmt0 = (v) =>
  '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

// Consolidate a raw SoFi description into a merchant name: drop store numbers
// (#5002), long id runs, and trailing codes so repeat visits group together.
function merchantKey(desc) {
  return desc
    .toUpperCase()
    .replace(/#\s*\d+/g, '')
    .replace(/\b\d{3,}\b/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim() || desc.toUpperCase();
}

export default function CategoryDetail({ transactions, category, color, onBack, onRecategorize }) {
  const items = transactions
    .filter(t => !t.isCredit && t.category === category)
    .sort((a, b) => b.date.localeCompare(a.date));

  const total = items.reduce((s, t) => s + Math.abs(t.amount), 0);
  const count = items.length;
  const avg = count ? total / count : 0;
  const largest = items.reduce((m, t) => Math.max(m, Math.abs(t.amount)), 0);

  // Months spanned (across the whole dataset) for a fair monthly average.
  const allMonths = new Set(transactions.map(t => t.month));
  const monthCount = Math.max(allMonths.size, 1);
  const perMonth = total / monthCount;

  // Group by merchant.
  const merchantMap = {};
  for (const t of items) {
    const key = merchantKey(t.description);
    if (!merchantMap[key]) merchantMap[key] = { name: key, count: 0, total: 0 };
    merchantMap[key].count += 1;
    merchantMap[key].total += Math.abs(t.amount);
  }
  const merchants = Object.values(merchantMap).sort((a, b) => b.total - a.total);

  // Monthly totals for this category.
  const monthMap = {};
  for (const t of items) {
    monthMap[t.month] = (monthMap[t.month] || 0) + Math.abs(t.amount);
  }
  const months = Object.entries(monthMap)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([month, amt]) => ({
      month,
      amt,
      label: new Date(month + '-02').toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
    }));

  const title = category.charAt(0).toUpperCase() + category.slice(1);

  return (
    <div className="tab-content">
      <div className="detail-header">
        <button type="button" className="detail-back" onClick={onBack}>&larr; Back</button>
        <div className="detail-title-wrap">
          <span className="detail-dot" style={{ background: color }} />
          <h2 className="detail-title">{title}</h2>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Total Spent</span>
          <span className="stat-value red">{fmt0(total)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Transactions</span>
          <span className="stat-value">{count.toLocaleString()}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Avg / Transaction</span>
          <span className="stat-value">{fmt(avg)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Avg / Month</span>
          <span className="stat-value yellow">{fmt0(perMonth)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Largest</span>
          <span className="stat-value">{fmt(largest)}</span>
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">By Merchant</h3>
        <div className="category-list detail-list">
          {merchants.map(m => {
            const pct = total > 0 ? (m.total / total) * 100 : 0;
            return (
              <div key={m.name} className="category-row">
                <span className="category-name" title={m.name}>
                  {m.name} <span className="merchant-count">&times;{m.count}</span>
                </span>
                <div className="category-bar-track">
                  <div className="category-bar-fill" style={{ width: `${pct}%`, background: color }} />
                </div>
                <span className="category-amount">
                  {fmt0(m.total)} <span className="category-pct">({pct.toFixed(1)}%)</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {months.length > 1 && (
        <div className="chart-card">
          <h3 className="chart-title">By Month</h3>
          <div className="category-list">
            {months.map(m => {
              const max = Math.max(...months.map(x => x.amt));
              const pct = max > 0 ? (m.amt / max) * 100 : 0;
              return (
                <div key={m.month} className="category-row">
                  <span className="category-name">{m.label}</span>
                  <div className="category-bar-track">
                    <div className="category-bar-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="category-amount">{fmt0(m.amt)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="chart-card">
        <h3 className="chart-title">All Transactions ({count})</h3>
        <p className="chart-hint">Wrong category? Reassign any transaction with the dropdown.</p>
        <div className="txn-table-wrap">
          <table className="txn-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th className="text-right">Amount</th>
                {onRecategorize && <th>Category</th>}
              </tr>
            </thead>
            <tbody>
              {items.map(t => (
                <tr key={t.id}>
                  <td className="txn-date">{t.date}</td>
                  <td className="txn-desc" title={t.description}>{t.description}</td>
                  <td className="txn-amount text-right red">-{fmt(t.amount)}</td>
                  {onRecategorize && (
                    <td>
                      <select
                        className="recat-select"
                        value={t.category}
                        onChange={e => onRecategorize(t.id, e.target.value)}
                      >
                        {CATEGORY_OPTIONS.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
