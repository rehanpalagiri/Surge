import { verdictDisplay } from "@/lib/verdicts";

interface VerdictBannerProps {
  verdict: string;
}

export default function VerdictBanner({ verdict }: VerdictBannerProps) {
  const v = verdictDisplay(verdict);

  return (
    <div className={`w-full rounded-2xl border ${v.bannerClass} p-6 md:p-8 text-center`}>
      <h1 className={`text-3xl md:text-4xl font-bold mb-2 ${v.textClass}`}>{v.label}</h1>
      <p className="text-text-muted text-sm">AI-assessed observable craft—not a performance forecast</p>
    </div>
  );
}
