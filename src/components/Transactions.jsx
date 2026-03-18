// MIT License - Copyright (c) 2024 Finance App

import { useState } from 'react';

const CATEGORIES = [
  'all', 'income', 'groceries', 'dining', 'subscriptions',
  'utilities', 'debt', 'transfer', 'discretionary',
];

const fmt = (v) =>
  '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Transactions({ transactions }) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const filtered = transactions.filter(t => {
    const catMatch = filter === 'all' || t.category === filter;
    const searchMatch = !search || t.description.toLowerCase().includes(search.toLowerCase());
    return catMatch && searchMatch;
  });

  return (
    <div className="tab-content">
      <div className="txn-controls">
        <input
          className="search-input"
          type="search"
          placeholder="Search transactions..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select
          className="filter-select"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        >
          {CATEGORIES.map(c => (
            <option key={c} value={c}>
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <p className="txn-count">{filtered.length.toLocaleString()} transactions</p>

      <div className="txn-table-wrap">
        <table className="txn-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Category</th>
              <th className="text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(t => (
              <tr key={t.id}>
                <td className="txn-date">{t.date}</td>
                <td className="txn-desc" title={t.description}>{t.description}</td>
                <td>
                  <span className={`badge badge-${t.category}`}>{t.category}</span>
                </td>
                <td className={`txn-amount text-right ${t.isCredit ? 'green' : 'red'}`}>
                  {t.isCredit ? '+' : '-'}{fmt(t.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
