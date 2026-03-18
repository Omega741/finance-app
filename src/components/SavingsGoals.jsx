// MIT License - Copyright (c) 2024 Finance App

import { useState } from 'react';

const fmt = (v) =>
  '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const EMPTY_FORM = { name: '', target: '', current: '', deadline: '' };

export default function SavingsGoals({ goals, onAdd, onUpdate, onDelete }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [editId, setEditId] = useState(null);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.name || !form.target) return;
    const goal = {
      ...form,
      target: parseFloat(form.target),
      current: parseFloat(form.current || 0),
    };
    if (editId) {
      onUpdate({ ...goal, id: editId });
      setEditId(null);
    } else {
      onAdd({ ...goal, id: Date.now().toString() });
    }
    setForm(EMPTY_FORM);
  };

  const startEdit = (goal) => {
    setEditId(goal.id);
    setForm({
      name: goal.name,
      target: String(goal.target),
      current: String(goal.current),
      deadline: goal.deadline || '',
    });
  };

  const cancelEdit = () => {
    setEditId(null);
    setForm(EMPTY_FORM);
  };

  return (
    <div className="tab-content">
      <div className="goal-form-card">
        <h3 className="form-title">{editId ? 'Edit Goal' : 'New Savings Goal'}</h3>
        <form className="goal-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <input
              className="form-input"
              placeholder="Goal name (e.g. Emergency Fund)"
              value={form.name}
              onChange={set('name')}
              required
            />
            <input
              className="form-input"
              type="number"
              placeholder="Target amount ($)"
              value={form.target}
              onChange={set('target')}
              min="1"
              step="0.01"
              required
            />
            <input
              className="form-input"
              type="number"
              placeholder="Amount saved so far ($)"
              value={form.current}
              onChange={set('current')}
              min="0"
              step="0.01"
            />
            <input
              className="form-input"
              type="date"
              placeholder="Target date"
              value={form.deadline}
              onChange={set('deadline')}
            />
          </div>
          <div className="form-actions">
            <button className="btn-primary" type="submit">
              {editId ? 'Update Goal' : 'Add Goal'}
            </button>
            {editId && (
              <button className="btn-ghost" type="button" onClick={cancelEdit}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>

      {goals.length === 0 ? (
        <p className="empty-state">No savings goals yet. Add one above to start tracking your progress.</p>
      ) : (
        <div className="goals-grid">
          {goals.map(goal => {
            const pct = Math.min((goal.current / goal.target) * 100, 100);
            const remaining = Math.max(goal.target - goal.current, 0);
            const complete = pct >= 100;
            return (
              <div key={goal.id} className={`goal-card ${complete ? 'complete' : ''}`}>
                <div className="goal-header">
                  <h4 className="goal-name">{goal.name}</h4>
                  <div className="goal-actions">
                    <button className="btn-icon" onClick={() => startEdit(goal)}>Edit</button>
                    <button className="btn-icon danger" onClick={() => onDelete(goal.id)}>Delete</button>
                  </div>
                </div>

                <div className="goal-amounts">
                  <span className="goal-current">{fmt(goal.current)}</span>
                  <span className="goal-sep"> / </span>
                  <span className="goal-target">{fmt(goal.target)}</span>
                </div>

                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{ width: `${pct}%` }}
                  />
                </div>

                <div className="goal-footer">
                  <span className="goal-pct">{pct.toFixed(0)}% complete</span>
                  {complete ? (
                    <span className="goal-done">Goal reached!</span>
                  ) : (
                    <span className="goal-remaining">
                      {fmt(remaining)} to go{goal.deadline ? ` by ${goal.deadline}` : ''}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
