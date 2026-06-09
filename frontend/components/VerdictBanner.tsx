interface VerdictBannerProps {
  verdict: string;
  predictedViews: string;
  predictedLikes?: string;
  platform?: string;
}

export default function VerdictBanner({
  verdict,
  predictedViews,
  predictedLikes,
  platform = "tiktok",
}: VerdictBannerProps) {
  const isHigh = verdict === "High potential";
  const isAvg = verdict === "Average potential";
  const isInstagram = platform === "instagram";

  const bgClass = isHigh
    ? "from-green-900/60 to-green-800/40 border-success/30"
    : isAvg
    ? "from-yellow-900/60 to-yellow-800/40 border-warning/30"
    : "from-red-900/60 to-red-800/40 border-danger/30";

  const textClass = isHigh
    ? "text-success"
    : isAvg
    ? "text-warning"
    : "text-danger";

  const icon = isHigh ? "🏆" : isAvg ? "📊" : "🔧";
  const hasLikes = !!predictedLikes && predictedLikes !== "Unknown";

  return (
    <div
      className={`w-full rounded-2xl border bg-gradient-to-br ${bgClass} p-6 md:p-8 text-center`}
    >
      <div className="text-5xl mb-3">{icon}</div>
      <h1 className={`text-3xl md:text-4xl font-bold mb-3 ${textClass}`}>
        {verdict}
      </h1>

      {isInstagram ? (
        /* Instagram: likes are the primary metric */
        <>
          {hasLikes && (
            <p className="text-text-primary text-lg font-semibold">
              {predictedLikes} predicted likes
            </p>
          )}
          <p className="text-text-muted text-sm mt-1">
            Predicted views:{" "}
            <span className="text-text-muted/80">{predictedViews}</span>
            <span className="text-text-muted/50 text-xs ml-1">(Instagram hides real views)</span>
          </p>
        </>
      ) : (
        /* TikTok: views are the primary metric */
        <>
          <p className="text-text-muted text-lg">
            Predicted views:{" "}
            <span className="text-text-primary font-semibold">{predictedViews}</span>
          </p>
          {hasLikes && (
            <p className="text-text-muted text-base mt-1">
              Predicted likes:{" "}
              <span className="text-text-primary font-semibold">{predictedLikes}</span>
            </p>
          )}
        </>
      )}
    </div>
  );
}
