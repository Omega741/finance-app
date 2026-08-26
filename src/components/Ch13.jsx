// MIT License - Copyright (c) 2024 Finance App

import { useState } from 'react';
import { ch13Totals } from '../utils/ch13';

const fmt0 = (v) => '$' + Math.round(Math.abs(v)).toLocaleString('en-US');
const fmt2 = (v) => '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Ch13({ claims, onImport, targets, onSetTarget }) {
  const [extra, setExtra] = useState(0);

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => onImport(ev.target.result);
    reader.readAsText(file);
    e.target.value = '';
  };

  const payment = targets.__ch13_payment ?? 805;

  const importBtn = (
    <label className="btn-primary" style={{ cursor: 'pointer' }}>
      {claims.length ? 'Re-import Claim Summary CSV' : 'Import Claim Summary CSV'}
      <input type="file" accept=".csv" hidden onChange={handleFile} />
    </label>
  );

  if (!claims.length) {
    return (
      <div className="tab-content">
        <h2 className="detail-title">Chapter 13 Payoff</h2>
        <div className="chart-card">
          <p className="chart-hint">
            Download your <strong>Claim Summary</strong> CSV from the National Data Center
            (ndc.org → your case → Claims → Export), then import it here. Your case data stays in
            your browser only — it is never uploaded or committed anywhere.
          </p>
          {importBtn}
        </div>
      </div>
    );
  }

  const { totalClaims, totalPaid, totalOwed } = ch13Totals(claims);
  const pct = totalClaims > 0 ? (totalPaid / totalClaims) * 100 : 0;

  // Finish-early math on the remaining principal owed to all claims.
  const monthsAt = (mo) => (mo > 0 ? Math.ceil(totalOwed / mo) : null);
  const baseMonths = monthsAt(payment);
  const fastMonths = monthsAt(payment + Number(extra || 0));
  const saved = baseMonths != null && fastMonths != null ? baseMonths - fastMonths : null;

  const rows = claims
    .filter((c) => c.claimAmount > 0)
    .sort((a, b) => b.claimAmount - a.claimAmount);

  return (
    <div className="tab-content">
      <div className="budget-head">
        <h2 className="detail-title">Chapter 13 Payoff</h2>
        {importBtn}
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Total Debt (claims)</span>
          <span className="stat-value">{fmt0(totalClaims)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Paid to Claims</span>
          <span className="stat-value green">{fmt0(totalPaid)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Remaining</span>
          <span className="stat-value red">{fmt0(totalOwed)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Monthly Payment</span>
          <input
            className="budget-income-input"
            type="number"
            value={payment}
            onChange={(e) => onSetTarget('__ch13_payment', parseFloat(e.target.value) || 0)}
          />
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Progress — {pct.toFixed(1)}% of claims paid</h3>
        <div className="category-bar-track" style={{ height: '16px' }}>
          <div className="category-bar-fill" style={{ width: `${Math.min(pct, 100)}%`, background: 'var(--green)' }} />
        </div>
        <p className="chart-hint" style={{ marginTop: '0.75rem' }}>
          Every claim on your plan is at <strong>0% interest</strong> — your balance never grows, so
          there's no rush. Early in a Chapter 13, payments clear the trustee's fee and your attorney
          first, so creditor balances start dropping faster from here.
        </p>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Finish Early Calculator</h3>
        <p className="chart-hint">
          Since it's a 100% plan, paying extra actually shortens it. See what an extra amount per
          month would do (approximate — run any real change past your attorney via a plan modification).
        </p>
        <div className="budget-row" style={{ gridTemplateColumns: '160px 120px 1fr', marginTop: '0.5rem' }}>
          <span className="budget-cat">Extra per month</span>
          <input
            className="budget-target-input"
            type="number"
            value={extra}
            min="0"
            onChange={(e) => setExtra(parseFloat(e.target.value) || 0)}
          />
          <span />
        </div>
        <div className="stat-grid" style={{ marginTop: '1rem' }}>
          <div className="stat-card">
            <span className="stat-label">At {fmt0(payment)}/mo</span>
            <span className="stat-value">{baseMonths ?? '—'} mo</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">At {fmt0(payment + Number(extra || 0))}/mo</span>
            <span className="stat-value">{fastMonths ?? '—'} mo</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Time Saved</span>
            <span className="stat-value green">
              {saved != null ? `${saved} mo (~${(saved / 12).toFixed(1)} yr)` : '—'}
            </span>
          </div>
        </div>
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Creditors ({rows.length})</h3>
        <div className="txn-table-wrap">
          <table className="txn-table">
            <thead>
              <tr>
                <th>Creditor</th>
                <th>Type</th>
                <th className="text-right">Claim</th>
                <th className="text-right">Paid</th>
                <th className="text-right">Remaining</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={c.creditor + i}>
                  <td className="txn-desc" title={c.creditor}>{c.creditor}</td>
                  <td><span className="badge badge-debt">{c.type.toLowerCase()}</span></td>
                  <td className="text-right">{fmt2(c.claimAmount)}</td>
                  <td className="text-right green">{fmt2(c.principalPaid)}</td>
                  <td className="text-right red">{fmt2(c.principalOwed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
