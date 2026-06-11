import Link from "next/link";

export const metadata = { title: "Terms of Service — Surge" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
      <div className="text-text-muted text-sm leading-relaxed space-y-3">{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-background">
      <nav className="border-b border-border bg-surface/50 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <Link href="/" className="font-bold text-xl gradient-text">Surge</Link>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Terms of Service</h1>
          <p className="text-text-muted text-sm mt-1">Effective date: June 10, 2026</p>
        </div>

        <Section title="Who can use Surge">
          <p>You must be 13 or older to create an account and use Surge.</p>
        </Section>

        <Section title="What Surge is">
          <p>
            Surge is a tool that helps you analyze your own short-form video content
            before you post it. It is <span className="text-text-primary font-medium">not
            a guarantee of viral performance</span> — predictions are estimates based
            on patterns, not promises.
          </p>
        </Section>

        <Section title="Your content">
          <p>
            You own your content. By uploading a video you grant Surge permission to
            process it for analysis (it is deleted from our servers immediately
            after). By linking a post URL you grant Surge permission to read that
            post&apos;s public engagement metrics.
          </p>
          <p>
            If you opt into the seed pool (available to users 18+ only), you grant
            Surge a non-exclusive license to use your post&apos;s public engagement
            data — never the video itself — as benchmark reference data for scoring
            other creators&apos; videos. You can revoke this at any time in Settings.
          </p>
        </Section>

        <Section title="Acceptable use">
          <p>
            We can suspend or terminate accounts that abuse the platform — including
            automated scraping, attempting to circumvent rate limits, or submitting
            content you don&apos;t have the rights to.
          </p>
        </Section>

        <Section title="No warranty">
          <p>
            Surge is provided &quot;as is&quot;. Predictions, scores, and
            recommendations are estimates for informational purposes and come with no
            warranty of accuracy or fitness for a particular purpose.
          </p>
        </Section>

        <Section title="Governing law">
          <p>These terms are governed by the laws of the State of Texas.</p>
        </Section>

        <div className="border-t border-border pt-6 text-sm text-text-muted">
          See also our{" "}
          <Link href="/privacy" className="text-purple-to hover:underline">Privacy Policy</Link>.
        </div>
      </div>
    </main>
  );
}
