const numberFormat = new Intl.NumberFormat("es-ES");
const decimalFormat = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return numberFormat.format(Number(value));
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toLocaleString("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} %`;
}

export function formatMinutes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  const text = Number.isInteger(number) ? numberFormat.format(number) : decimalFormat.format(number);
  return `${text} min`;
}

export function toDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value) {
  const date = toDate(value);
  if (!date) return "—";
  return `${datePart(date)} ${timePart(date)} UTC`;
}

export function formatDateTimeSeconds(value) {
  const date = toDate(value);
  if (!date) return "—";
  return `${datePart(date)} ${timePart(date, true)} UTC`;
}

export function formatTimeSeconds(value) {
  const date = toDate(value);
  if (!date) return "—";
  return `${timePart(date, true)} UTC`;
}

export function isoDatePart(value) {
  const date = toDate(value);
  if (!date) return "";
  return datePart(date);
}

function datePart(date) {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

function timePart(date, withSeconds = false) {
  const base = `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
  return withSeconds ? `${base}:${pad(date.getUTCSeconds())}` : base;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

export function plural(count, singular, pluralForm) {
  return count === 1 ? singular : pluralForm;
}

export function datetimeLocalToUtcIso(value) {
  if (!value) return null;
  const parsed = new Date(`${value}:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export function utcIsoToDatetimeLocal(value) {
  const date = toDate(value);
  if (!date) return "";
  return `${datePart(date)}T${timePart(date)}`;
}
