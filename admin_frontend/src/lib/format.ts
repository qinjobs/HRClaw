import {
  finalDecisionLabels,
  reasonCodeLabels,
  stageLabels,
  systemDecisionLabels,
} from "@/lib/constants";

export function formatTime(value?: string | null) {
  return value || "-";
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
