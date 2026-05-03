import { Entry } from "@/lib/supabase";

type Props = { entries: Entry[]; topLanes: number[] };

export default function ScoreTable({ entries, topLanes }: Props) {
  const sorted = [...entries].sort(
    (a, b) => (b.entry_score ?? 0) - (a.entry_score ?? 0)
  );

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="bg-gray-100 text-gray-600 text-xs">
          <th className="text-left p-2">艇</th>
          <th className="text-left p-2">選手</th>
          <th className="text-left p-2">級別</th>
          <th className="text-right p-2">スコア</th>
          <th className="text-right p-2">展示T</th>
          <th className="text-right p-2">展示ST</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((e) => {
          const isTop = topLanes.includes(e.lane);
          return (
            <tr
              key={e.lane}
              className={`border-t ${isTop ? "bg-yellow-50 font-semibold" : ""}`}
            >
              <td className="p-2">{e.lane}号艇</td>
              <td className="p-2">{e.racer_name}</td>
              <td className="p-2 text-gray-500">{e.racer_class ?? "-"}</td>
              <td className="p-2 text-right">
                {e.entry_score !== null ? `${e.entry_score}点` : "-"}
              </td>
              <td className="p-2 text-right">
                {e.exhibition_time !== null ? e.exhibition_time.toFixed(2) : "-"}
              </td>
              <td className="p-2 text-right">
                {e.exhibition_st !== null ? e.exhibition_st.toFixed(3) : "-"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
