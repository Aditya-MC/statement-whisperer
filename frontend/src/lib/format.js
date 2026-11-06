// Display helpers. Amounts arrive from the API as decimal strings and are only formatted here,
// never used for arithmetic.

const moneyCache = new Map();

export function formatMoney(amount, currency = "USD", locale = undefined) {
  if (amount === null || amount === undefined || amount === "") return "";
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  const key = `${locale}|${currency}`;
  let fmt = moneyCache.get(key);
  if (!fmt) {
    try {
      fmt = new Intl.NumberFormat(locale, { style: "currency", currency });
    } catch {
      fmt = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    moneyCache.set(key, fmt);
  }
  return fmt.format(n);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2024-01-05" -> "05 Jan 2024" (parsed by hand to avoid timezone shifts). */
export function formatDate(iso) {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

export function amountTone(amount) {
  const n = Number(amount);
  if (n > 0) return "text-emerald-600 dark:text-emerald-400";
  if (n < 0) return "text-zinc-900 dark:text-zinc-100";
  return "text-zinc-500";
}
