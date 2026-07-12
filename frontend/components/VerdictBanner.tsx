import { verdictDisplay } from "@/lib/verdicts";

interface VerdictBannerProps {
  verdict: string;
  /** Lowest-scoring applicable dimension, surfaced so a positive verdict stays
   *  honest about an outlier (e.g. "Strong craft" above an Ending Strength 5/10). */
  weakest?: { label: string; score: number } | null;
}

export default function VerdictBanner({ verdict, weakest }: VerdictBannerProps) {
  const v = verdictDisplay(verdict);
  // Only call out the weakest dimension on an otherwise-positive verdict, and only
  // when it's below "solid" — on an early-craft verdict the whole thing is weak, so
  // singling one out would be noise.
  const showWeakest =
    !!weakest && (v.tone === "strong" || v.tone === "developing") && weakest.score < 7;

  return (
    <div className={`w-full rounded-2xl border ${v.bannerClass} p-6 md:p-8 text-center`}>
      <h1 className={`text-3xl md:text-4xl font-bold mb-2 ${v.textClass}`}>{v.label}</h1>
      <p className="text-text-muted text-sm">AI-assessed observable craft—not a performance forecast</p>
      {showWeakest && (
        <p className="text-text-muted text-xs mt-3">
          Watch your weakest dimension:{" "}
          <span className="text-warning font-medium">
            {weakest!.label} ({weakest!.score}/10)
          </span>
        </p>
      )}
    </div>
  );
}
