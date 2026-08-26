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

  // Chapter 13 payoff tracker (TFS only shows payments, not the plan total).
  const ch13Payment = targets.__ch13_payment ?? 806;
  const ch13Total = targets.__ch13_total ?? 0;
  const ch13Paid = targets.__ch13_paid ?? 0;
  const ch13Pct = ch13Total > 0 ? Math.min((ch13Paid / ch13Total) * 100, 100) : 0;
  const ch13Remaining = Math.max(ch13Total - ch13Paid, 0);
  const ch13MonthsLeft = ch13Payment > 0 && ch13Total > 0 ? Math.ceil(ch13Remaining / ch13Payment) : null;

  const targetFor = (cat) => targets[cat] ?? RECOMMENDED_TARGETS[cat] ?? 0;

  const rows = BUDGET_CATEGORIES
    .map((cat) => ({ cat, target: targetFor(cat), actual: actuals[cat] || 0 }))
    .sort((a, b) => b.target - a.target);

  const totalTarget = rows.reduce((s, r) => s + r.target, 0);
  const totalActual = rows.reduce((s, r) => s + r.actual, 0);
  const planned = totalTarget + savings + sinking;   // spending targets + savings
  const surplus = income - planned;

  const alreadyHasEF = goals?.some((g) => /emergency/i.test(g.name));

  const createEmergencyGoal = () => {
    onAddGoal({
      id: Date.now().toString(),
      name: 'Emergency Fund (starter)',
      target: 1000,
      current: 0,
      deadline: '',
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
          <p className="chart-hint">An emergency-fund goal already exists in your Goals tab. ✓</p>
        ) : (
          <button type="button" className="btn-primary" onClick={createEmergencyGoal}>
            Create emergency-fund goal
          </button>
        )}
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Chapter 13 Payoff Progress</h3>
        <p className="chart-hint">
          TFS Bill Pay only <em>processes</em> your payments — it doesn't hold your plan total, so it
          can't show progress. Get your exact figures free at the National Data Center
          (ndc.org): total paid in, claims, and balance. Enter them here to track it.
        </p>
        <div className="stat-grid">
          <div className="stat-card">
            <span className="stat-label">Total plan amount</span>
            <input className="budget-income-input" type="number" value={ch13Total}
              onChange={(e) => onSetTarget('__ch13_total', parseFloat(e.target.value) || 0)} />
          </div>
          <div className="stat-card">
            <span className="stat-label">Paid so far</span>
            <input className="budget-income-input" type="number" value={ch13Paid}
              onChange={(e) => onSetTarget('__ch13_paid', parseFloat(e.target.value) || 0)} />
          </div>
          <div className="stat-card">
            <span className="stat-label">Monthly payment</span>
            <input className="budget-income-input" type="number" value={ch13Payment}
              onChange={(e) => onSetTarget('__ch13_payment', parseFloat(e.target.value) || 0)} />
          </div>
        </div>
        <div className="category-bar-track" style={{ height: '14px', marginTop: '1rem' }}>
          <div className="category-bar-fill" style={{ width: `${ch13Pct}%`, background: 'var(--green)' }} />
        </div>
        <div className="budget-total-row">
          <span>{ch13Pct.toFixed(0)}% paid</span>
          <span>{fmt0(ch13Remaining)} remaining</span>
          {ch13MonthsLeft != null && <span>~{ch13MonthsLeft} payments left</span>}
        </div>
        <p className="chart-hint">
          Note: whether paying extra actually finishes it sooner depends on your plan type (100% vs
          partial) — confirm with your trustee/attorney before paying more.
        </p>
      </div>
    </div>
  );
}
