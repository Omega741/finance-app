// MIT License - Copyright (c) 2024 Finance App

// Keywords are matched as substrings of the lowercased merchant description.
// categorize() checks lists in a specific -> general ORDER and the first match
// wins, so where two lists could both match (e.g. "frys fuel" vs "frys #5002"),
// the ordering in categorize() decides. Tokens reflect how SoFi actually writes
// merchant names (e.g. "FRYS #5002", "COX COMM PHX", "ROCKET MORTGAGE").

// Checked BEFORE groceries so "frys fuel" lands in transportation, not groceries.
const TRANSPORTATION_KEYWORDS = [
  'fuel', 'gas station', 'chevron', 'circle k', 'quiktrip', 'qt ', 'shell oil',
  'arco', 'exxon', 'mobil', 'texaco', 'valero', 'speedway', 'wawa', 'racetrac',
  'car wash', 'blast off', "o'reilly", 'oreilly', 'autozone', 'auto parts',
  'jiffy lube', 'discount tire', 'honda of', 'toyota of', 'parking', 'dmv',
  'uber trip', 'lyft', 'metro transit',
];

const GROCERY_KEYWORDS = [
  'kroger', 'safeway', 'whole foods', 'trader joe', 'walmart', 'wal-mart',
  'wm supercenter', 'costco', 'publix', 'aldi', 'wegmans', 'heb', 'meijer',
  'sprouts', 'food lion', 'stop shop', 'giant', 'albertsons', 'winco',
  'grocery', 'frys', "fry's", 'harris teeter', 'winn dixie', 'food 4 less',
  'smart final', 'stater bros', 'vons', 'ralphs', 'shop rite', 'fresh market',
  'natural grocers', 'bashas', 'food city',
];

const DINING_KEYWORDS = [
  'restaurant', 'mcdonald', 'burger king', "wendy's", 'taco bell', 'taco',
  'chick-fil-a', 'chick fil', 'chickfila', 'starbucks', 'dunkin', 'chipotle',
  'subway', 'domino', 'pizza', 'papa john', 'doordash', 'uber eats', 'grubhub',
  'postmates', 'cafe', 'coffee', 'diner', 'grill', 'kitchen', 'eatery', 'bistro',
  'steakhouse', 'sushi', 'panera', 'chili', 'applebee', 'olive garden',
  'red lobster', 'redlobster', 'ihop', "denny's", 'waffle', 'cracker barrel',
  'outback', 'longhorn', 'panda express', 'jack in the box', 'sonic', 'canes',
  'whataburger', 'five guys', 'fiveguys', 'shake shack', 'dairy queen', 'popeyes',
  'kfc', 'in-n-out', 'in n out', 'senor taco', 'arby', 'carls jr', "carl's",
  'krispy kreme', 'einstein', 'barros', 'crumbl', 'saddle bronc', 'knuckle',
  'forefathers', 'dickey', 'melty', 'sauce  inc', 'jimmy g', 'bbq', 'nakedq',
];

const SUBSCRIPTION_KEYWORDS = [
  'netflix', 'hulu', 'disney', 'hbo max', 'peacock', 'paramount',
  'amazon prime', 'prime video', 'amazon music', 'apple music', 'apple.com',
  'spotify', 'pandora', 'tidal', 'youtube premium', 'google one', 'icloud',
  'dropbox', 'microsoft 365', 'office 365', 'adobe', 'canva', 'figma',
  'subscription', 'membership', 'audible', 'simplisafe', 'anthropic', 'claude',
  'patreon', 'discord nitro', 'xbox game pass', 'playstation plus', 'paddle',
  'nintendo switch online', 'duolingo', 'headspace', 'noom', 'peloton',
];

const UTILITY_KEYWORDS = [
  'electric', 'electricity', 'power co', 'energy', 'natural gas', 'gas co',
  'water', 'sewer', 'waste management', 'trash', 'garbage', 'recycling',
  'internet', 'broadband', 'cable', 'satellite', 'srp', 'salt river',
  'city of mesa', 'aps ', 'verizon', 'at&t', 't-mobile', 'tmobile', 'sprint',
  'boost mobile', 'metro pcs', 'cricket wireless', 'comcast', 'xfinity',
  'spectrum', 'cox comm', 'cox communic', 'optimum', 'frontier', 'centurylink',
  "pg&e", 'duke energy', 'con edison', 'coned', 'dominion energy',
  'southern company', 'entergy', 'ameren', 'exelon', 'pseg',
  'phone bill', 'cell phone', 'wireless bill', 'utility',
];

const HOUSING_KEYWORDS = [
  'mortgage', 'rocket mortgage', 'apartment', 'leasing', 'realty', ' hoa',
  'hoa ', 'cortina vista', 'property mgmt', 'property management',
  'homeowners assoc', 'landlord',
];

const INSURANCE_KEYWORDS = [
  'state farm', 'geico', 'progressive', 'allstate', 'insurance', 'usaa',
  'farmers ins', 'liberty mutual', 'nationwide', 'aetna', 'cigna',
  'blue cross', 'metlife',
];

const EDUCATION_KEYWORDS = [
  'univ of phx', 'university', 'tuition', 'college', 'campus', 'coursera',
  'udemy', 'edx', 'chegg',
];

// Checked BEFORE healthcare so "animal hospital" lands in pets, not healthcare.
const PET_KEYWORDS = [
  'petsmart', 'petco', 'chewy', 'animal hospi', 'animal hospital',
  'veterinar', 'vet clinic', 'pet supplies', 'pet supermarket',
];

const HEALTHCARE_KEYWORDS = [
  'pharmacy', 'cvs', 'walgreens', 'rite aid', 'cardio', 'cardiology',
  'neurology', 'medical', 'clinic', 'hospital', 'dental', 'dentist', ' dds',
  'optometry', 'urgent care', 'physicians', 'wellness', 'med*', 'labcorp',
  'quest diag',
];

const DEBT_KEYWORDS = [
  'loan payment', 'auto loan', 'car payment', 'student loan',
  'credit card payment', 'card payment', 'minimum payment', 'tfs ',
  'toyota financial', 'toyota fin', 'chase credit', 'capital one', 'citibank',
  'citi card', 'bank of america', 'wells fargo', 'discover card',
  'american express', 'amex', 'synchrony', 'barclays', 'ally financial',
  'navient', 'sallie mae', 'great lakes', 'fedloan', 'nelnet', 'mohela',
  'sofi loan', 'affirm', 'klarna', 'afterpay',
];

// Money moved to savings/investing accounts — not spending, not income.
const TRANSFER_KEYWORDS = [
  'fid bkg', 'fidelity', 'coinbase', 'robinhood', 'acorns', 'wealthfront',
  'to savings', 'vanguard',
];

const INCOME_KEYWORDS = [
  'direct deposit', 'payroll', 'salary', 'wages', 'paycheck',
  'employer', 'compensation', 'ach deposit', 'income deposit',
];

// All categories a transaction can be manually reassigned to (used by the
// re-categorize dropdowns). "reimbursed" = money that left the account but was
// paid back to you (e.g. employer tuition reimbursement via paycheck).
export const CATEGORY_OPTIONS = [
  'housing', 'groceries', 'dining', 'transportation', 'utilities',
  'subscriptions', 'insurance', 'healthcare', 'education', 'debt', 'pets',
  'transfer', 'reimbursed', 'discretionary', 'income',
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
  // Order matters: specific/essential buckets first, catch-all last.
  if (TRANSPORTATION_KEYWORDS.some(k => desc.includes(k))) return 'transportation';
  if (GROCERY_KEYWORDS.some(k => desc.includes(k))) return 'groceries';
  if (DINING_KEYWORDS.some(k => desc.includes(k))) return 'dining';
  if (SUBSCRIPTION_KEYWORDS.some(k => desc.includes(k))) return 'subscriptions';
  if (UTILITY_KEYWORDS.some(k => desc.includes(k))) return 'utilities';
  if (HOUSING_KEYWORDS.some(k => desc.includes(k))) return 'housing';
  if (INSURANCE_KEYWORDS.some(k => desc.includes(k))) return 'insurance';
  if (EDUCATION_KEYWORDS.some(k => desc.includes(k))) return 'education';
  if (PET_KEYWORDS.some(k => desc.includes(k))) return 'pets';
  if (HEALTHCARE_KEYWORDS.some(k => desc.includes(k))) return 'healthcare';
  if (DEBT_KEYWORDS.some(k => desc.includes(k))) return 'debt';
  if (TRANSFER_KEYWORDS.some(k => desc.includes(k))) return 'transfer';
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
