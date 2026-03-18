# Finance App

## Project Overview
A personal finance PWA (Progressive Web App) with AI-powered analysis. The user uploads their bank CSV exports (SoFi) and the app parses, categorizes, and visualizes their financial data. An embedded Claude AI chat allows the user to ask questions about their finances and receive personalized advice based on their actual data.

## Repository
- GitHub: https://github.com/Omega741/finance-app

## Tech Stack
- Frontend: React (PWA)
- Styling: Tailwind CSS
- Charts: Recharts
- AI: Anthropic Claude API (claude-sonnet-4-20250514)
- Build: Vite
- Storage: localStorage for session, artifact storage for persistence

## Key Features
- CSV upload and parsing (SoFi format)
- Transaction categorization engine (direct deposit, Zelle, groceries, dining, subscriptions, utilities, debt payments, discretionary)
- Monthly income vs spending dashboard
- Net worth tracker
- Savings goals
- Interactive financial flowchart advisor based on real user data
- Claude AI chat window with full access to user's financial data for personalized advice

## Project Structure
- /src - React app source
- /src/components - UI components
- /src/utils - CSV parser, categorization engine
- /src/ai - Claude API integration
- /skills - SKILL.md files
- CLAUDE.md - this file
- .env - API keys (never commit)
- .gitignore - excludes CSV files, .env, node_modules

## Development Setup
```bash
npm install
npm run dev
```

## Common Commands
```bash
npm run dev       # start dev server
npm run build     # production build
npm run preview   # preview production build
```

## Rules
- Never commit .env or any CSV files
- Never hardcode personal data
- Always return full corrected code when making changes
- No dashes in output or comments
- Keep components small and focused
- Validate all CSV input at the parser boundary
- MIT license on all files
