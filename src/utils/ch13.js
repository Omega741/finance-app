// MIT License - Copyright (c) 2024 Finance App
//
// Parser for the National Data Center (ndc.org) "Claim Summary" CSV export of a
// Chapter 13 case. Parsed data is kept in the browser (localStorage) only — it
// is never committed, so personal case/creditor data stays private.

function parseLine(line) {
  const out = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') inQ = !inQ;
    else if (ch === ',' && !inQ) { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out.map(s => s.trim().replace(/^"|"$/g, '').trim());
}

function money(v) {
  const n = parseFloat(String(v).replace(/[$,\s]/g, ''));
  return isNaN(n) ? 0 : n;
}

export function parseClaimSummary(text) {
  const lines = text.trim().split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) throw new Error('Claim Summary CSV appears empty.');

  const headers = parseLine(lines[0]).map(h => h.toLowerCase());
  const idx = (name) => headers.findIndex(h => h.includes(name));
  const iCred = idx('creditor name');
  const iDesc = idx('claim description');
  const iClaim = idx('claim amount');
  const iPaid = idx('principal paid');
  const iOwed = idx('principal owed');
  const iRate = idx('interest rate');

  if (iCred === -1 || iClaim === -1) {
    throw new Error('This does not look like an NDC Claim Summary CSV (missing Creditor/Claim columns).');
  }

  const claims = [];
  for (let i = 1; i < lines.length; i++) {
    const r = parseLine(lines[i]);
    const creditor = r[iCred];
    if (!creditor) continue;
    const claimAmount = money(r[iClaim]);
    claims.push({
      creditor,
      type: (iDesc !== -1 ? r[iDesc] : '') || 'CLAIM',
      claimAmount,
      principalPaid: iPaid !== -1 ? money(r[iPaid]) : 0,
      principalOwed: iOwed !== -1 ? money(r[iOwed]) : claimAmount,
      interestRate: iRate !== -1 ? money(r[iRate]) : 0,
    });
  }
  if (claims.length === 0) throw new Error('No claims found in the CSV.');
  return claims;
}

export function ch13Totals(claims) {
  return claims.reduce(
    (t, c) => ({
      totalClaims: t.totalClaims + c.claimAmount,
      totalPaid: t.totalPaid + c.principalPaid,
      totalOwed: t.totalOwed + c.principalOwed,
    }),
    { totalClaims: 0, totalPaid: 0, totalOwed: 0 }
  );
}
