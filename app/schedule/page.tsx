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

export default async function SchedulePage() {
  const today = todayJST();
  const { rows, summary } = await getScheduleData(today);
  return <ScheduleClient rows={rows} summary={summary} today={today} />;
}
