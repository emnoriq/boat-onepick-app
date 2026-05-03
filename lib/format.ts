export function formatCloseTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
}

export function decisionLabel(decision: string): string {
  return { buy: "買い", candidate: "候補", skip: "見送り" }[decision] ?? decision;
}

export function rankColor(confidence: number): string {
  if (confidence >= 92) return "text-red-600 font-bold";
  if (confidence >= 88) return "text-orange-500 font-semibold";
  if (confidence >= 80) return "text-yellow-600";
  return "text-gray-400";
}

export function rankLabel(confidence: number): string {
  if (confidence >= 92) return "S";
  if (confidence >= 88) return "A";
  if (confidence >= 80) return "B";
  return "C";
}

export function hitLabel(isHit: boolean | null): string {
  if (isHit === null) return "未確定";
  return isHit ? "的中" : "不的中";
}
