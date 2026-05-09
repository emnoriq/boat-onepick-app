import { getScheduleData } from "@/lib/supabase";
import ScheduleClient from "./ScheduleClient";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date()
    .toLocaleDateString("ja-JP", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
    .replace(/\//g, "-");
}

/** URLパラメータの date が有効な YYYY-MM-DD かどうか検証 */
function isValidDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(Date.parse(s));
}

type Props = { searchParams: { date?: string } };

export default async function SchedulePage({ searchParams }: Props) {
  const today = todayJST();
  const reqDate = searchParams.date;
  const date = reqDate && isValidDate(reqDate) ? reqDate : today;
  const { rows, summary } = await getScheduleData(date);
  return <ScheduleClient rows={rows} summary={summary} today={today} date={date} />;
}
