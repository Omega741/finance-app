// MIT License - Copyright (c) 2024 Finance App

import { useState, useEffect } from 'react';
import { parseCSV } from './utils/csvParser';
import CSVUpload from './components/CSVUpload';
import Dashboard from './components/Dashboard';
import Transactions from './components/Transactions';
import SavingsGoals from './components/SavingsGoals';
import NetWorth from './components/NetWorth';
import Chat from './components/Chat';

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'networth', label: 'Net Worth' },
  { id: 'goals', label: 'Goals' },
  { id: 'chat', label: 'AI Chat' },
];

function loadStored() {
  try {
    const raw = localStorage.getItem('finance_transactions');
    if (!raw) return { transactions: [], lastUpdated: null };
    const { transactions, lastUpdated } = JSON.parse(raw);
    return { transactions: transactions || [], lastUpdated: lastUpdated || null };
  } catch {
    return { transactions: [], lastUpdated: null };
  }
}

function loadGoals() {
  try {
    return JSON.parse(localStorage.getItem('finance_goals') || '[]');
  } catch {
    return [];
  }
}

function fmtTimestamp(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' at ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

export default function App() {
  const stored = loadStored();
  const [transactions, setTransactions] = useState(stored.transactions);
  const [lastUpdated, setLastUpdated] = useState(stored.lastUpdated);
  const [goals, setGoals] = useState(loadGoals);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [uploadError, setUploadError] = useState('');

  useEffect(() => {
    localStorage.setItem('finance_goals', JSON.stringify(goals));
  }, [goals]);

  const handleFileInput = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => handleCSVText(ev.target.result);
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleCSVText = (text) => {
    try {
      const txns = parseCSV(text);
      const now = new Date().toISOString();
      setTransactions(txns);
      setLastUpdated(now);
      setUploadError('');
      localStorage.setItem('finance_transactions', JSON.stringify({ transactions: txns, lastUpdated: now }));
    } catch (err) {
      setUploadError(err.message);
    }
  };

  const addGoal = (goal) => setGoals(prev => [...prev, goal]);
  const updateGoal = (goal) => setGoals(prev => prev.map(g => g.id === goal.id ? goal : g));
  const deleteGoal = (id) => setGoals(prev => prev.filter(g => g.id !== id));

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <div className="header-brand">
            <span className="brand-mark">$</span>
            <span className="brand-name">FinanceApp</span>
          </div>
          <div className="header-right">
            {transactions.length > 0 && (
              <div className="header-meta">
                <span className="header-txn-count">{transactions.length.toLocaleString()} transactions</span>
                {lastUpdated && (
                  <span className="header-last-updated">Last updated: {fmtTimestamp(lastUpdated)}</span>
                )}
              </div>
            )}
            <label className="btn-upload">
              {transactions.length > 0 ? 'Replace CSV' : 'Upload CSV'}
              <input type="file" accept=".csv" hidden onChange={handleFileInput} />
            </label>
          </div>
        </div>
      </header>

      <main className="app-main">
        {uploadError && (
          <div className="global-error">
            {uploadError}
            <button className="error-dismiss" onClick={() => setUploadError('')}>x</button>
          </div>
        )}

        {transactions.length === 0 ? (
          <CSVUpload onUpload={handleCSVText} />
        ) : (
          <>
            <nav className="tabs-nav">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {activeTab === 'dashboard' && <Dashboard transactions={transactions} />}
            {activeTab === 'transactions' && <Transactions transactions={transactions} />}
            {activeTab === 'networth' && <NetWorth transactions={transactions} />}
            {activeTab === 'goals' && (
              <SavingsGoals
                goals={goals}
                onAdd={addGoal}
                onUpdate={updateGoal}
                onDelete={deleteGoal}
              />
            )}
            {activeTab === 'chat' && <Chat transactions={transactions} />}
          </>
        )}
      </main>
    </div>
  );
}
