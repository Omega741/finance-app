# Finance App

A personal finance PWA with AI-powered analysis. Upload your SoFi bank CSV exports and the app parses, categorizes, and visualizes your financial data. An embedded Claude AI chat lets you ask questions about your finances and receive personalized advice based on your actual transaction data.

## Features

- CSV upload and parsing (SoFi format, drag and drop)
- Automatic transaction categorization (income, groceries, dining, subscriptions, utilities, debt, transfer, discretionary)
- Monthly income vs spending dashboard with bar charts
- Transaction table with search and category filter
- Net worth trend with cumulative and monthly line charts
- Savings goals with progress tracking, persisted to localStorage
- AI chat powered by Claude with full access to your financial data
- Chat history persisted across page reloads with one-click clear
- Transaction data persisted to localStorage, restored automatically on load
- Installable as a PWA with service worker and offline support
- Dark theme, mobile friendly

## Tech Stack

- React 19 + Vite
- Recharts for data visualization
- Anthropic Claude API (claude-sonnet-4-20250514)
- Tailwind-inspired custom CSS (dark theme)
- localStorage for persistence
- PWA manifest + service worker

## Setup

1. Clone the repo

```bash
git clone https://github.com/Omega741/finance-app.git
cd finance-app
```

2. Install dependencies

```bash
npm install
```

3. Create a `.env` file in the root with your Anthropic API key

```
VITE_ANTHROPIC_API_KEY=your_api_key_here
```

4. Start the dev server

```bash
npm run dev
```

5. Open http://localhost:5173 and upload your SoFi CSV export

## Usage

- **Dashboard** — bar chart of monthly income vs spending, category breakdown
- **Transactions** — searchable, filterable table of all transactions with category badges
- **Net Worth** — cumulative net worth trend and monthly net income line charts
- **Goals** — add savings goals with target amounts and deadlines, track progress
- **AI Chat** — ask Claude anything about your finances; it has full context of your data

## CSV Format

Designed for SoFi checking and savings account CSV exports. The parser detects columns automatically and handles both `MM/DD/YYYY` and `YYYY-MM-DD` date formats.

## Security Note

This is a personal local tool. The Anthropic API key is stored in `.env` (never committed) and sent directly from the browser using the `anthropic-dangerous-direct-browser-access` header, which is Anthropic's official opt-in for browser usage. Do not deploy this app publicly.

## License

MIT License. See [LICENSE](LICENSE).
