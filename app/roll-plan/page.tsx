import { getScheduleData } from "@/lib/supabase";
import { buildRollPlan } from "@/lib/rollPlan";
import RollPlanClient from "./RollPlanClient";

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

export default async function RollPlanPage() {
  const today = todayJST();
  const { rows } = await getScheduleData(today);
  const plan = buildRollPlan(rows);
  return <RollPlanClient plan={plan} today={today} />;
}
