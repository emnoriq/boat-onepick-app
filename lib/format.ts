// 場コード → boatrace.jp JCD マッピング
const STADIUM_JCD: Record<string, string> = {
  桐生: "01", 戸田: "02", 江戸川: "03", 平和島: "04",
  多摩川: "05", 浜名湖: "06", 蒲郡: "07", 常滑: "08",
  津: "09", 三国: "10", びわこ: "11", 住之江: "12",
  尼崎: "13", 鳴門: "14", 丸亀: "15", 児島: "16",
  宮島: "17", 徳山: "18", 下関: "19", 若松: "20",
  芦屋: "21", 福岡: "22", 唐津: "23", 大村: "24",
};

/** boatrace.jp の出走表 URL を生成 */
export function buildBoatraceUrl(
  stadium: string,
  raceDate: string, // "2026-05-17"
  raceNo: number,
): string {
  const jcd = STADIUM_JCD[stadium];
  if (!jcd) return "https://www.boatrace.jp";
  const hd = raceDate.replace(/-/g, "");
  return `https://www.boatrace.jp/owpc/pc/race/racelist?jcd=${jcd}&hd=${hd}&rno=${raceNo}`;
}

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
