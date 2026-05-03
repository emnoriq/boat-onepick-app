import { decisionLabel } from "@/lib/format";

type Props = { decision: string };

const styles: Record<string, string> = {
  buy:       "bg-red-100 text-red-700 border-red-300",
  candidate: "bg-orange-100 text-orange-700 border-orange-300",
  skip:      "bg-gray-100 text-gray-500 border-gray-300",
};

export default function PredictionBadge({ decision }: Props) {
  const cls = styles[decision] ?? styles.skip;
  return (
    <span className={`text-xs font-bold border rounded-full px-2 py-0.5 ${cls}`}>
      {decisionLabel(decision)}
    </span>
  );
}
