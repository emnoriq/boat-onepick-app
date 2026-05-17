import { decisionLabel } from "@/lib/format";

type Props = { decision: string };

export default function PredictionBadge({ decision }: Props) {
  const cls =
    decision === "buy"       ? "text-white"     :
    decision === "candidate" ? "text-white"      :
                               "bg-gray-100 text-gray-400";

  const style =
    decision === "buy"       ? { background: "linear-gradient(to right, #FF6B6B, #FF8E53)" } :
    decision === "candidate" ? { background: "linear-gradient(to right, #FF8E53, #FFBE0B)" } :
                               {};

  return (
    <span className={`text-xs font-bold rounded-full px-3 py-1 ${cls}`} style={style}>
      {decisionLabel(decision)}
    </span>
  );
}
