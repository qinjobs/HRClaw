import {
  finalDecisionLabels,
  reasonCodeLabels,
  stageLabels,
  systemDecisionLabels,
} from "@/lib/constants";

function _pad(value: number) {
  return String(value).padStart(2, "0");
}

function _parseDateTime(value?: string | null): Date | null {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const normalized = raw.replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized);
  if (hasTimezone) {
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(normalized)) {
    const withSeconds = normalized.length === 16 ? `${normalized}:00` : normalized;
    const parsed = new Date(`${withSeconds}Z`);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  const fallback = new Date(raw);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

export function formatTime(value?: string | null) {
  const date = _parseDateTime(value);
  if (!date) return value || "-";
  return `${date.getFullYear()}-${_pad(date.getMonth() + 1)}-${_pad(date.getDate())} ${_pad(date.getHours())}:${_pad(date.getMinutes())}:${_pad(date.getSeconds())}`;
}

export function formatStage(value?: string | null) {
  return value ? stageLabels[value] || value : "-";
}

export function formatReasonCode(value?: string | null) {
  return value ? reasonCodeLabels[value] || value : "-";
}

export function formatDecision(value?: string | null) {
  return value ? systemDecisionLabels[value] || finalDecisionLabels[value] || value : "-";
}

export function formatScore(value?: number | null) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "-"
    : Number(value).toFixed(1);
}

export function toDateTimeLocal(value?: string | null) {
  if (!value) return "";
  if (value.includes("T")) return value.slice(0, 16);
  return value.replace(" ", "T").slice(0, 16);
}

export function fromDateTimeLocal(value?: string | null) {
  return value?.trim() ? value.trim() : null;
}

export function compactText(value?: string | null, limit = 140) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit).trimEnd()}...` : text;
}

export function humanBool(value?: boolean | null) {
  if (value === true) return "是";
  if (value === false) return "否";
  return "-";
}

export function safeList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
}
