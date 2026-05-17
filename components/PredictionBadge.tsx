import { decisionLabel } from "@/lib/format";

type Props = { decision: string };

const styles: Record<string, string> = {
  buy:       "bg-emerald-500 text-white",
  candidate: "bg-amber-400 text-white",
  skip:      "bg-gray-100 text-gray-500",
};

export default function PredictionBadge({ decision }: Props) {
  const cls = styles[decision] ?? styles.skip;
  return (
    <span className={`text-xs font-bold rounded-full px-3 py-1 ${cls}`}>
      {decisionLabel(decision)}
    </span>
  );
}
