import Link from "next/link";
import BrandLogo from "@/components/BrandLogo";

export const metadata = { title: "Privacy Policy — Surge" };

function Section({ title, id, children }: { title: string; id?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="space-y-3">
      <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
      <div className="text-text-muted text-sm leading-relaxed space-y-3">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-background">
      <nav className="border-b border-border bg-surface/50 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <BrandLogo className="text-xl" />
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Privacy Policy</h1>
          <p className="text-text-muted text-sm mt-1">Effective date: June 10, 2026</p>
        </div>

        <Section title="Who we are">
          <p>
            Surge is a video analysis tool operated as a sole proprietorship in the
            United States. Questions or requests about your data:{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>.
          </p>
          <p>This policy applies to users in the United States.</p>
        </Section>

        <Section title="What we collect">
          <ul className="list-disc pl-5 space-y-1.5">
            <li>Your email address and a username</li>
            <li>Your password — stored only as a secure hash, never in plain text</li>
            <li>Your full date of birth (used solely to verify the age requirement)</li>
            <li>Your content niche (the free-text description you provide)</li>
            <li>Video captions and profile bios you type into the analyzer</li>
            <li>TikTok or Instagram post URLs you choose to link to an analysis</li>
            <li>
              Public metrics from linked posts, including observation time and post age
            </li>
          </ul>
        </Section>

        <Section title="What we do NOT collect or store">
          <p className="text-text-primary font-medium">
            We never retain your video files.
          </p>
          <p>
            Every video you upload is sent to Google Gemini for analysis and
            permanently deleted from our servers within seconds of the analysis
            completing. There is no copy of your video on Surge&apos;s
            infrastructure after that point.
          </p>
        </Section>

        <Section title="Google Gemini">
          <p>
            Videos are processed by Google&apos;s Gemini API. Google&apos;s privacy
            policy applies to that processing. We have no control over Google&apos;s
            handling of data sent to their API. You can review Google&apos;s policy
            at{" "}
            <a
              href="https://policies.google.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              policies.google.com/privacy
            </a>.
          </p>
        </Section>

        <Section title="Optional measurement research" id="measurement-research">
          <p>
            If you are <span className="text-text-primary font-medium">18 or older</span>{" "}
            <em>and</em> have opted in via your Settings, the public engagement data
            from your linked social media posts — including counts, observation time,
            post URL, and content niche — may be used for measurement research and
            same-age comparisons. They are not treated as proof of causation.
          </p>
          <p className="text-text-primary font-medium">
            Your actual video is never used — only the numbers.
          </p>
          <p>
            Users under 18 are permanently excluded from measurement research. You can opt
            out or change your preference at any time in Settings → Data &amp;
            Privacy.
          </p>
        </Section>

        <Section title="Data retention & deletion">
          <p>
            Account data is retained until you delete your account. You can request
            full deletion of your account and all associated data by emailing{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>.
          </p>
        </Section>

        <Section title="Children">
          <p>
            Surge is available to users 13 and older. Users under 13 may not create
            an account. Public metrics from users aged 13–17 are excluded from
            measurement research and cannot be opted in.
          </p>
        </Section>

        <Section title="California residents (CCPA)">
          <p>
            If you are a California resident, you have the right to request that we
            disclose what personal data we hold about you, to request deletion of
            that data, and to opt out of the sale of personal data.{" "}
            <span className="text-text-primary font-medium">
              We do not sell your personal data.
            </span>{" "}
            To exercise any of these rights, email{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>.
          </p>
        </Section>

        <Section title="Changes to this policy">
          <p>
            If we make material changes, we&apos;ll update the effective date at the
            top of this page. Continued use of Surge after changes means you accept
            the updated policy.
          </p>
        </Section>

        <div className="border-t border-border pt-6 text-sm text-text-muted">
          See also our{" "}
          <Link href="/terms" className="text-accent hover:underline">Terms of Service</Link>.
        </div>
      </div>
    </main>
  );
}
