interface VerdictBannerProps {
  verdict: string;
}

export default function VerdictBanner({ verdict }: VerdictBannerProps) {
  const isHigh = verdict === "Strong craft" || verdict === "High potential";
  const isAvg = verdict === "Developing craft" || verdict === "Average potential";

  const bgClass = isHigh
    ? "from-green-900/60 to-green-800/40 border-success/30"
    : isAvg
    ? "from-yellow-900/60 to-yellow-800/40 border-warning/30"
    : "from-red-900/60 to-red-800/40 border-danger/30";

  const textClass = isHigh ? "text-success" : isAvg ? "text-warning" : "text-danger";
  const icon = isHigh ? "🏆" : isAvg ? "📊" : "🔧";

  return (
    <div className={`w-full rounded-2xl border bg-gradient-to-br ${bgClass} p-6 md:p-8 text-center`}>
      <div className="text-5xl mb-3">{icon}</div>
      <h1 className={`text-3xl md:text-4xl font-bold mb-2 ${textClass}`}>{verdict}</h1>
      <p className="text-text-muted text-sm">AI-assessed observable craft—not a performance forecast</p>
    </div>
  );
}
