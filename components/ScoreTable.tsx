import { Entry } from "@/lib/supabase";

type Props = { entries: Entry[]; topLanes: number[] };

function fmt1(v: number | null): string {
  return v !== null ? v.toFixed(1) : "-";
}
function fmt2(v: number | null): string {
  return v !== null ? v.toFixed(2) : "-";
}
function fmt3(v: number | null): string {
  return v !== null ? v.toFixed(3) : "-";
}

export default function ScoreTable({ entries, topLanes }: Props) {
  const sorted = [...entries].sort(
    (a, b) => (b.entry_score ?? 0) - (a.entry_score ?? 0)
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-100 text-gray-600 text-xs">
            <th className="text-left p-2 whitespace-nowrap">艇</th>
            <th className="text-left p-2 whitespace-nowrap">選手</th>
            <th className="text-left p-2 whitespace-nowrap">級</th>
            <th className="text-right p-2 whitespace-nowrap">スコア</th>
            <th className="text-right p-2 whitespace-nowrap">展示T</th>
            <th className="text-right p-2 whitespace-nowrap">展示ST</th>
            <th className="text-right p-2 whitespace-nowrap">チルト</th>
            <th className="text-right p-2 whitespace-nowrap">進入</th>
            <th className="text-right p-2 whitespace-nowrap">M率</th>
            <th className="text-right p-2 whitespace-nowrap">B率</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((e) => {
            const isTop = topLanes.includes(e.lane);
            // 進入コースがレーン番号と異なる場合は色付け
            const approachMoved = e.approach_lane !== null && e.approach_lane !== e.lane;
            const approachInner = approachMoved && e.approach_lane! < e.lane;  // インに動いた
            return (
              <tr
                key={e.lane}
                className={`border-t ${isTop ? "bg-yellow-50 font-semibold" : ""}`}
              >
                <td className="p-2 font-bold">{e.lane}号艇</td>
                <td className="p-2">{e.racer_name}</td>
                <td className="p-2 text-gray-500">{e.racer_class ?? "-"}</td>
                <td className="p-2 text-right font-mono">
                  {e.entry_score !== null ? `${e.entry_score}` : "-"}
                </td>
                <td className="p-2 text-right font-mono">
                  {fmt2(e.exhibition_time)}
                </td>
                <td className="p-2 text-right font-mono text-xs">
                  {fmt3(e.exhibition_st)}
                </td>
                <td className="p-2 text-right font-mono text-xs">
                  {e.tilt !== null ? (
                    <span className={
                      e.tilt >= 0.5 && e.tilt <= 2.0 ? "text-green-600 font-bold" :
                      e.tilt > 2.0 ? "text-orange-500" :
                      "text-gray-500"
                    }>
                      {e.tilt > 0 ? `+${e.tilt.toFixed(1)}` : e.tilt.toFixed(1)}
                    </span>
                  ) : "-"}
                </td>
                <td className="p-2 text-right font-mono text-xs">
                  {e.approach_lane !== null ? (
                    <span className={
                      approachInner ? "text-blue-600 font-bold" :
                      approachMoved ? "text-orange-500" :
                      "text-gray-600"
                    }>
                      {e.approach_lane}コース
                      {approachInner ? "↑" : approachMoved ? "↓" : ""}
                    </span>
                  ) : "-"}
                </td>
                <td className="p-2 text-right font-mono text-xs text-gray-600">
                  {fmt1(e.motor_rate)}%
                </td>
                <td className="p-2 text-right font-mono text-xs text-gray-600">
                  {fmt1(e.boat_rate)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
