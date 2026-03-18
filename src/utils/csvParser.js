// MIT License - Copyright (c) 2024 Finance App

const GROCERY_KEYWORDS = [
  'kroger', 'safeway', 'whole foods', 'trader joe', 'walmart', 'costco',
  'publix', 'aldi', 'wegmans', 'heb', 'meijer', 'sprouts', 'food lion',
  'stop shop', 'giant', 'albertsons', 'winco', 'grocery', 'market basket',
  'harris teeter', 'winn dixie', 'food 4 less', 'smart final', 'stater bros',
  'vons', 'ralphs', 'frys food', 'shop rite', 'fresh market', 'natural grocers',
];

const DINING_KEYWORDS = [
  'restaurant', 'mcdonald', 'burger king', "wendy's", 'taco bell', 'chick-fil-a',
  'starbucks', 'dunkin', 'chipotle', 'subway', 'domino', 'pizza hut', 'papa john',
  'doordash', 'uber eats', 'grubhub', 'postmates',
  'cafe', 'coffee', 'diner', 'grill', 'kitchen', 'eatery', 'bistro', 'steakhouse',
  'sushi', 'panera', 'chilis', 'applebee', 'olive garden', 'red lobster', 'ihop',
  "denny's", 'waffle house', 'cracker barrel', 'outback', 'longhorn',
  'panda express', 'jack in the box', 'sonic drive', 'raising cane',
  'whataburger', 'five guys', 'shake shack', 'dairy queen', 'popeyes', 'kfc',
];

const SUBSCRIPTION_KEYWORDS = [
  'netflix', 'hulu', 'disney', 'hbo max', 'peacock', 'paramount',
  'amazon prime', 'amazon music', 'apple music', 'spotify', 'pandora',
  'tidal', 'youtube premium', 'google one', 'icloud', 'dropbox',
  'microsoft 365', 'office 365', 'adobe', 'canva', 'figma',
  'subscription', 'membership', 'annual fee', 'monthly fee',
  'patreon', 'discord nitro', 'xbox game pass', 'playstation plus',
  'nintendo switch online', 'duolingo', 'headspace', 'calm', 'noom',
  'peloton', 'beachbody',
];

const UTILITY_KEYWORDS = [
  'electric', 'electricity', 'power co', 'energy', 'natural gas', 'gas co',
  'water', 'sewer', 'waste management', 'trash', 'garbage', 'recycling',
  'internet', 'broadband', 'cable tv', 'satellite',
  'verizon', 'at&t', 'att ', 't-mobile', 'tmobile', 'sprint', 'boost mobile',
  'metro pcs', 'cricket wireless', 'comcast', 'xfinity', 'spectrum',
  'cox communications', 'optimum', 'frontier', 'centurylink',
  "pg&e", 'pge ', 'duke energy', 'con edison', 'coned', 'dominion energy',
  'southern company', 'entergy', 'ameren', 'exelon', 'pseg',
  'phone bill', 'cell phone', 'wireless bill', 'utility bill',
];

const DEBT_KEYWORDS = [
  'loan payment', 'mortgage payment', 'auto loan', 'car payment', 'student loan',
  'credit card payment', 'card payment', 'minimum payment',
  'chase credit', 'capital one', 'citibank', 'citi card', 'bank of america',
  'wells fargo', 'discover card', 'american express', 'amex',
  'synchrony', 'barclays', 'ally financial', 'navient', 'sallie mae',
  'great lakes', 'fedloan', 'nelnet', 'mohela',
  'sofi loan', 'sofi personal loan',
];

const INCOME_KEYWORDS = [
  'direct deposit', 'payroll', 'salary', 'wages', 'paycheck',
  'employer', 'compensation', 'ach deposit', 'income deposit',
];

function parseAmount(value) {
  if (typeof value === 'number') return value;
  const cleaned = String(value)
    .replace(/[$,\s]/g, '')
    .replace('(', '-')
    .replace(')', '');
  return parseFloat(cleaned) || 0;
}

function parseDate(value) {
  if (!value) return null;
  const trimmed = value.trim();

  const mmddyyyy = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (mmddyyyy) {
    return `${mmddyyyy[3]}-${mmddyyyy[1].padStart(2, '0')}-${mmddyyyy[2].padStart(2, '0')}`;
  }

  if (/^\d{4}-\d{2}-\d{2}/.test(trimmed)) return trimmed.slice(0, 10);

  const d = new Date(trimmed);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return null;
}

function categorize(description, isCredit) {
  const desc = description.toLowerCase();

  if (isCredit) {
    if (INCOME_KEYWORDS.some(k => desc.includes(k))) return 'income';
    if (desc.includes('zelle')) return 'income';
    if (desc.includes('transfer from') || desc.includes('mobile deposit')) return 'income';
    return 'income';
  }

  if (desc.includes('zelle')) return 'transfer';
  if (GROCERY_KEYWORDS.some(k => desc.includes(k))) return 'groceries';
  if (DINING_KEYWORDS.some(k => desc.includes(k))) return 'dining';
  if (SUBSCRIPTION_KEYWORDS.some(k => desc.includes(k))) return 'subscriptions';
  if (UTILITY_KEYWORDS.some(k => desc.includes(k))) return 'utilities';
  if (DEBT_KEYWORDS.some(k => desc.includes(k))) return 'debt';
  return 'discretionary';
}

function detectColumns(headers) {
  const h = headers.map(col => col.toLowerCase().replace(/[^a-z\s]/g, '').trim());

  const find = (...candidates) => {
    for (const c of candidates) {
      const idx = h.findIndex(col => col.includes(c));
      if (idx !== -1) return idx;
    }
    return -1;
  };

  return {
    date: find('transaction date', 'date'),
    description: find('description', 'name', 'memo', 'payee', 'merchant'),
    amount: find('amount'),
    type: find('transaction type', 'type'),
    status: find('status'),
  };
}

function parseRow(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim().replace(/^"|"$/g, ''));
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim().replace(/^"|"$/g, ''));
  return result;
}

export function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) throw new Error('CSV file appears empty or invalid.');

  const headers = parseRow(lines[0]);
  const cols = detectColumns(headers);

  if (cols.date === -1 || cols.description === -1 || cols.amount === -1) {
    throw new Error(
      'Could not detect required columns (Date, Description, Amount). Please verify this is a SoFi CSV export.'
    );
  }

  const transactions = [];

  for (let i = 1; i < lines.length; i++) {
    const row = parseRow(lines[i]);
    if (row.length < 3) continue;

    const dateStr = row[cols.date] || '';
    const description = (row[cols.description] || '').trim();
    const rawAmount = row[cols.amount] || '0';
    const typeStr = cols.type !== -1 ? (row[cols.type] || '').toLowerCase() : '';
    const status = cols.status !== -1 ? (row[cols.status] || '').toLowerCase() : '';

    if (status === 'pending') continue;
    if (!description) continue;

    const amount = parseAmount(rawAmount);
    const date = parseDate(dateStr);
    if (!date) continue;

    let isCredit;
    if (typeStr) {
      if (typeStr.includes('credit') || typeStr.includes('deposit') || typeStr.includes('incoming')) {
        isCredit = true;
      } else if (
        typeStr.includes('debit') || typeStr.includes('withdrawal') ||
        typeStr.includes('payment') || typeStr.includes('pos') || typeStr.includes('ach')
      ) {
        isCredit = false;
      } else {
        isCredit = amount >= 0;
      }
    } else {
      isCredit = amount >= 0;
    }

    const category = categorize(description, isCredit);
    const month = date.slice(0, 7);
    const absAmount = Math.abs(amount);

    transactions.push({
      id: `${date}-${i}-${absAmount}`,
      date,
      description,
      amount: isCredit ? absAmount : -absAmount,
      category,
      month,
      isCredit,
    });
  }

  if (transactions.length === 0) {
    throw new Error('No valid transactions found. Check that the CSV contains Date, Description, and Amount columns.');
  }

  return transactions.sort((a, b) => b.date.localeCompare(a.date));
}

export function getMonthlyData(transactions) {
  const map = {};
  for (const t of transactions) {
    if (!map[t.month]) map[t.month] = { month: t.month, income: 0, spending: 0 };
    if (t.isCredit) {
      map[t.month].income += t.amount;
    } else {
      map[t.month].spending += Math.abs(t.amount);
    }
  }
  return Object.values(map)
    .sort((a, b) => a.month.localeCompare(b.month))
    .map(m => ({
      ...m,
      label: new Date(m.month + '-02').toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      net: m.income - m.spending,
    }));
}

export function getCategoryTotals(transactions) {
  const map = {};
  for (const t of transactions.filter(t => !t.isCredit)) {
    if (!map[t.category]) map[t.category] = 0;
    map[t.category] += Math.abs(t.amount);
  }
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .map(([category, total]) => ({ category, total }));
}

export function getNetWorthTrend(transactions) {
  const monthly = getMonthlyData(transactions);
  let cumulative = 0;
  return monthly.map(m => {
    cumulative += m.net;
    return { ...m, netWorth: cumulative };
  });
}
