// MIT License - Copyright (c) 2024 Finance App

import { useState } from 'react';
import { getMonths, getMonthlyCategoryTotals } from '../utils/csvParser';

const fmt0 = (v) => '$' + Math.round(Math.abs(v)).toLocaleString('en-US');
const signed = (v) => (v < 0 ? '-' : '+') + '$' + Math.round(Math.abs(v)).toLocaleString('en-US');

// Research-backed monthly targets (see the recovery plan). Editable in the UI.
export const RECOMMENDED_TARGETS = {
  housing: 2040, debt: 770, groceries: 425, utilities: 375, dining: 450,
  insurance: 131, transportation: 175, discretionary: 325, subscriptions: 110,
  healthcare: 85, pets: 70, education: 60,
};
const BUDGET_CATEGORIES = Object.keys(RECOMMENDED_TARGETS);
const DEFAULT_INCOME = 5850;
const SAVINGS_TARGET = 500;   // pay-yourself-first, emergency fund
const SINKING_TARGET = 200;   // travel / car / vet — lumpy costs

export default function Budget({ transactions, targets, onSetTarget, onAddGoal, goals }) {
  const months = getMonths(transactions);
  const [month, setMonth] = useState(months[months.length - 1] || '');

  const actuals = getMonthlyCategoryTotals(transactions, month);
  const income = targets.__income ?? DEFAULT_INCOME;
  const savings = targets.__savings ?? SAVINGS_TARGET;
  const sinking = targets.__sinking ?? SINKING_TARGET;

  const targetFor = (cat) => targets[cat] ?? RECOMMENDED_TARGETS[cat] ?? 0;

  const rows = BUDGET_CATEGORIES
    .map((cat) => ({ cat, target: targetFor(cat), actual: actuals[cat] || 0 }))
    .sort((a, b) => b.target - a.target);

  const totalTarget = rows.reduce((s, r) => s + r.target, 0);
  const totalActual = rows.reduce((s, r) => s + r.actual, 0);
  const planned = totalTarget + savings + sinking;   // spending targets + savings
  const surplus = income - planned;

  const alreadyHasEF = goals?.some((g) => /emergency/i.test(g.name));

  // The savings-first plan: a $1,000 starter cushion, then one month of essentials.
  const createEmergencyGoal = () => {
    const now = Date.now();
    [
      { name: 'Emergency Fund (starter)', target: 1000 },
      { name: 'Emergency Fund (1 month)', target: 4000 },
    ].forEach((w, i) => {
      if (!goals?.some((g) => g.name === w.name)) {
        onAddGoal({ id: (now + i).toString(), name: w.name, target: w.target, current: 0, deadline: '' });
      }
    });
  };

  return (
    <div className="tab-content">
      <div className="budget-head">
        <h2 className="detail-title">Monthly Budget</h2>
        <select className="filter-select" value={month} onChange={(e) => setMonth(e.target.value)}>
          {months.slice().reverse().map((m) => (
            <option key={m} value={m}>
              {new Date(m + '-02').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
            </option>
          ))}
        </select>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Monthly Income</span>
          <input
            className="budget-income-input"
            type="number"
            value={income}
            onChange={(e) => onSetTarget('__income', parseFloat(e.target.value) || 0)}
          />
        </div>
        <div className="stat-card">
          <span className="stat-label">Budgeted Spending</span>
          <span className="stat-value">{fmt0(totalTarget)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">To Savings + Sinking</span>
          <span className="stat-value green">{fmt0(savings + sinking)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Left Over</span>
          <span className={`stat-value ${surplus >= 0 ? 'green' : 'red'}`}>{signed(surplus)}</span>
        </div>
      </div>

      <div className="chart-card">
        <div className="budget-card-head">
          <h3 className="chart-title">Targets vs Actual — {month}</h3>
          <button type="button" className="btn-ghost" onClick={() => onSetTarget('__reset', Date.now())}>
            Reset to recommended
          </button>
        </div>
        <p className="chart-hint">
          Set a monthly target per category; the bar and the over/under fill from this month's
          actual spending. Edit any target — it saves automatically.
        </p>
        <div className="budget-list">
          {rows.map(({ cat, target, actual }) => {
            const pct = target > 0 ? Math.min((actual / target) * 100, 100) : 0;
            const over = actual > target;
            const diff = target - actual;
            return (
              <div key={cat} className="budget-row">
                <span className="budget-cat">{cat}</span>
                <input
                  className="budget-target-input"
                  type="number"
                  value={target}
                  onChange={(e) => onSetTarget(cat, parseFloat(e.target.value) || 0)}
                />
                <div className="category-bar-track">
                  <div
                    className="category-bar-fill"
                    style={{ width: `${pct}%`, background: over ? 'var(--red)' : 'var(--green)' }}
                  />
                </div>
                <span className="budget-actual">{fmt0(actual)}</span>
                <span className={`budget-diff ${over ? 'red' : 'green'}`}>
                  {over ? `${fmt0(-diff)} over` : `${fmt0(diff)} left`}
                </span>
              </div>
            );
          })}
        </div>
        <div className="budget-total-row">
          <span>Total</span>
          <span className="budget-target-total">{fmt0(totalTarget)} target</span>
          <span className={totalActual > totalTarget ? 'red' : 'green'}>{fmt0(totalActual)} actual</span>
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Savings &amp; Emergency Fund</h3>
        <p className="chart-hint">
          Pay yourself first: automate a transfer on payday <em>before</em> you can spend it.
          Automation, not willpower, is what makes this stick.
        </p>
        <div className="stat-grid">
          <div className="stat-card">
            <span className="stat-label">Auto-save / month</span>
            <input
              className="budget-income-input"
              type="number"
              value={savings}
              onChange={(e) => onSetTarget('__savings', parseFloat(e.target.value) || 0)}
            />
          </div>
          <div className="stat-card">
            <span className="stat-label">Sinking fund / month</span>
            <input
              className="budget-income-input"
              type="number"
              value={sinking}
              onChange={(e) => onSetTarget('__sinking', parseFloat(e.target.value) || 0)}
            />
          </div>
        </div>
        <ol className="ef-steps">
          <li><strong>$1,000 starter</strong> — your first cushion (~2 months at {fmt0(savings)}/mo).</li>
          <li><strong>1 month of essentials (~$4,100)</strong> — real breathing room.</li>
          <li><strong>3 months (~$12,300)</strong> — full safety net, incl. income disruption.</li>
        </ol>
        {alreadyHasEF ? (
          <p className="chart-hint">Your emergency-fund goals are set up — track them in the Goals tab. ✓</p>
        ) : (
          <button type="button" className="btn-primary" onClick={createEmergencyGoal}>
            Set up my savings goals
          </button>
        )}
        <p className="chart-hint" style={{ marginTop: '0.75rem' }}>
          Your Chapter 13 payoff — creditor breakdown, progress, and a finish-early calculator —
          now lives in its own <strong>Chapter 13</strong> tab.
        </p>
      </div>
    </div>
  );
}
