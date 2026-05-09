export function formatCloseTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
}

export function decisionLabel(decision: string): string {
  return { buy: "買い", candidate: "候補", skip: "見送り" }[decision] ?? decision;
}

/**
 * confidence → 表示色
 * 実際の confidence 分布に合わせて閾値を再設定 (scoring.py の出力範囲 ≈ 55〜82)
 *   S: ≥ 75  (buy tier 上位)
 *   A: ≥ 68  (buy / candidate 上位)
 *   B: ≥ 60  (candidate / watch)
 *   C: < 60  (skip)
 */
export function rankColor(confidence: number): string {
  if (confidence >= 75) return "text-red-600 font-bold";
  if (confidence >= 68) return "text-orange-500 font-semibold";
  if (confidence >= 60) return "text-yellow-600";
  return "text-gray-400";
}

export function rankLabel(confidence: number): string {
  if (confidence >= 75) return "S";
  if (confidence >= 68) return "A";
  if (confidence >= 60) return "B";
  return "C";
}

export function hitLabel(isHit: boolean | null): string {
  if (isHit === null) return "未確定";
  return isHit ? "的中" : "不的中";
}
