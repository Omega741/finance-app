// MIT License - Copyright (c) 2024 Finance App

import { getMonthlyData, getCategoryTotals } from '../utils/csvParser';

function buildFinancialContext(transactions) {
  if (!transactions || transactions.length === 0) {
    return 'No financial data has been loaded yet.';
  }

  const monthly = getMonthlyData(transactions);
  const categories = getCategoryTotals(transactions);
  const totalIncome = transactions
    .filter(t => t.isCredit)
    .reduce((s, t) => s + t.amount, 0);
  const totalSpending = transactions
    .filter(t => !t.isCredit)
    .reduce((s, t) => s + Math.abs(t.amount), 0);
  const months = [...new Set(transactions.map(t => t.month))].length;

  const recentTransactions = transactions
    .slice(0, 30)
    .map(t =>
      `${t.date}: ${t.description} ${t.isCredit ? '+' : '-'}$${Math.abs(t.amount).toFixed(2)} [${t.category}]`
    )
    .join('\n');

  const monthlyBreakdown = monthly
    .map(m =>
      `${m.label}: Income $${m.income.toFixed(2)}, Spending $${m.spending.toFixed(2)}, Net $${m.net.toFixed(2)}`
    )
    .join('\n');

  const categoryBreakdown = categories
    .map(c => `  ${c.category}: $${c.total.toFixed(2)}`)
    .join('\n');

  return `
FINANCIAL DATA SUMMARY
Period: ${months} month(s) of data, ${transactions.length} transactions total
Total Income:   $${totalIncome.toFixed(2)}
Total Spending: $${totalSpending.toFixed(2)}
Net Savings:    $${(totalIncome - totalSpending).toFixed(2)}
Savings Rate:   ${totalIncome > 0 ? (((totalIncome - totalSpending) / totalIncome) * 100).toFixed(1) : 0}%

MONTHLY BREAKDOWN:
${monthlyBreakdown}

SPENDING BY CATEGORY:
${categoryBreakdown}

RECENT TRANSACTIONS (last 30):
${recentTransactions}
`.trim();
}

export async function sendMessage(messages, transactions) {
  const apiKey = import.meta.env.VITE_ANTHROPIC_API_KEY;
  if (!apiKey || apiKey === 'your_api_key_here') {
    throw new Error('API key not configured. Set VITE_ANTHROPIC_API_KEY in your .env file.');
  }

  const financialContext = buildFinancialContext(transactions);

  const systemPrompt = `You are a personal finance advisor with access to the user's real transaction data. Be specific, concise, and reference their actual numbers. Give actionable advice.

${financialContext}`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 1024,
      system: systemPrompt,
      messages,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err?.error?.message || `API error ${response.status}`);
  }

  const data = await response.json();
  return data.content[0].text;
}
