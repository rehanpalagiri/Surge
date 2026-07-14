import Link from "next/link";
import { SITE_URL, SITE_HOST } from "@/lib/site";
import BrandLogo from "@/components/BrandLogo";

export const metadata = { title: "Terms of Service — Surge" };

function Section({ title, number, children }: { title: string; number: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <p className="text-xs font-medium text-text-muted uppercase tracking-widest">{number}</p>
      <h2 className="text-base font-semibold text-text-primary">{title}</h2>
      <div className="text-text-muted text-sm leading-relaxed space-y-3">{children}</div>
    </section>
  );
}

function CapsBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface border border-border rounded-lg px-4 py-3 text-xs font-medium text-text-primary leading-relaxed">
      {children}
    </div>
  );
}

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-background">
      <nav className="border-b border-border bg-surface/50 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <BrandLogo className="text-xl" />
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
        <div className="border-b border-border pb-6">
          <h1 className="text-2xl font-bold text-text-primary">Terms of Service</h1>
          <p className="text-text-muted text-sm mt-1">
            Surge &nbsp;·&nbsp; Effective date: June 26, 2026 &nbsp;·&nbsp; Governed by the laws of the State of Texas
          </p>
        </div>

        {/* Table of contents */}
        <div className="bg-surface border border-border rounded-xl px-5 py-4 space-y-2">
          <p className="text-xs font-medium text-text-muted uppercase tracking-widest mb-3">Contents</p>
          <ol className="list-decimal list-inside space-y-1 text-sm text-text-muted columns-2 gap-x-8">
            {[
              "Acceptance of Terms",
              "Changes to These Terms",
              "Description of Service",
              "Eligibility",
              "Account Registration and Security",
              "Usage Limits",
              "Your Content — Ownership and License",
              "Measurement Research Program",
              "Acceptable Use Policy",
              "AI-Generated Output Disclaimer",
              "Third-Party Services",
              "Intellectual Property",
              "Disclaimer of Warranties",
              "Limitation of Liability",
              "Indemnification",
              "Termination",
              "Dispute Resolution and Arbitration",
              "Governing Law and Venue",
              "General Provisions",
              "Contact Information",
            ].map((item) => (
              <li key={item} className="leading-relaxed">{item}</li>
            ))}
          </ol>
        </div>

        <Section number="Section 1" title="Acceptance of Terms">
          <p>
            By accessing or using Surge at {SITE_HOST} (the &quot;Service&quot;), creating an account, uploading
            content, or clicking any &quot;I agree&quot; button, you agree to be legally bound by these Terms of
            Service (&quot;Terms&quot;). If you do not agree to all of these Terms, you may not access or use the Service.
          </p>
          <p>
            These Terms constitute a binding legal agreement between you (&quot;User,&quot; &quot;you,&quot; or
            &quot;your&quot;) and Surge (&quot;Surge,&quot; &quot;we,&quot; &quot;us,&quot; or &quot;our&quot;), a sole
            proprietorship operating in the United States.
          </p>
          <p>
            If you are using the Service on behalf of an organization, you represent and warrant that you have the
            authority to bind that organization to these Terms, and references to &quot;you&quot; include that organization.
          </p>
        </Section>

        <Section number="Section 2" title="Changes to These Terms">
          <p>
            We reserve the right to modify these Terms at any time. When we make material changes, we will update the
            &quot;Effective date&quot; at the top of this page. We may also notify you by email or via an in-app notice,
            but we are not obligated to do so.
          </p>
          <p>
            Your continued use of the Service after the updated Terms become effective constitutes your acceptance of
            the revised Terms. If you do not agree to the updated Terms, you must stop using the Service and may
            request deletion of your account.
          </p>
          <p>
            Changes to pricing, usage limits, or the Measurement Research Program will be announced with at least
            14 days&apos; notice before taking effect.
          </p>
        </Section>

        <Section number="Section 3" title="Description of Service">
          <p>Surge is an AI-assisted retention craft review tool for short-form video content. The Service allows you to:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              Upload short-form video files for AI-powered retention craft analysis across six observable dimensions: hook
              velocity, cut frequency, text scannability, curiosity gap, audio-visual sync, and ending strength;
            </li>
            <li>
              Link public social media post URLs (TikTok, Instagram) to track observed engagement metrics over time;
            </li>
            <li>Review editing hypotheses and experiment recommendations generated for your content;</li>
            <li>
              Optionally participate in the Measurement Research Program (for eligible users aged 18 and older).
            </li>
          </ul>
          <p>
            Surge is an <span className="text-text-primary font-medium">outcome-blind craft reviewer and experiment
            tracker</span>. The Service does not predict, guarantee, or promise any specific reach, views, likes,
            follower growth, algorithmic distribution, or any other outcome on any social media platform. All dimension
            assessments are AI-assisted craft opinions, not measured retention or engagement forecasts.
          </p>
        </Section>

        <Section number="Section 4" title="Eligibility">
          <p>To use Surge, you must meet all of the following requirements:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              <span className="text-text-primary font-medium">Age:</span> You must be at least 13 years old. Users
              under 13 may not create an account or use the Service under any circumstances.
            </li>
            <li>
              <span className="text-text-primary font-medium">Minors (13–17):</span> If you are between 13 and 17
              years old, you may only use the Service with the consent and supervision of a parent or legal guardian.
              The Measurement Research Program is permanently unavailable to users under 18 and cannot be enabled
              under any circumstance.
            </li>
            <li>
              <span className="text-text-primary font-medium">Legal capacity:</span> You must have the legal capacity
              to enter into a binding agreement.
            </li>
            <li>
              <span className="text-text-primary font-medium">Not barred:</span> You must not be a person barred from
              using the Service under the laws of the United States or any other applicable jurisdiction.
            </li>
            <li>
              <span className="text-text-primary font-medium">Geographic scope:</span> The Service is operated from
              the United States and is intended for users in the United States. Access from outside the United States
              is at your own risk and subject to all applicable local laws.
            </li>
          </ul>
          <p>
            We reserve the right to request proof of age at any time and to terminate accounts that do not meet
            eligibility requirements.
          </p>
        </Section>

        <Section number="Section 5" title="Account Registration and Security">
          <p>To access most features of the Service, you must register for an account. When registering, you agree to:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              Provide accurate, current, and complete information, including your full date of birth (used solely to
              verify age eligibility);
            </li>
            <li>Maintain and promptly update your account information to keep it accurate and complete;</li>
            <li>
              Choose a strong password and keep it confidential — you are solely responsible for all activity that
              occurs under your account;
            </li>
            <li>
              Notify us immediately at{" "}
              <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
                surgeprivacy@gmail.com
              </a>{" "}
              if you suspect unauthorized access to your account.
            </li>
          </ul>
          <p>
            We store passwords only as secure cryptographic hashes and never in plain text. However, you are
            responsible for maintaining the security of your login credentials on your own devices.
          </p>
          <p>
            You may not create more than one account, transfer your account to another person, or use another
            user&apos;s account without their explicit permission. Accounts are non-transferable.
          </p>
          <p>
            We reserve the right to refuse registration, suspend, or terminate accounts at our sole discretion.
          </p>
        </Section>

        <Section number="Section 6" title="Usage Limits">
          <p>
            The Service operates under a rolling usage limit system to ensure fair access for all users:
          </p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              <span className="text-text-primary font-medium">Base limit:</span> Authenticated users may upload up to
              10 videos per 3-hour rolling window.
            </li>
            <li>
              <span className="text-text-primary font-medium">Bonus credits:</span> Users who have previously linked
              a verified social media post earn +1 bonus upload credit per unique verified post, up to a maximum of
              +10 bonus credits. The maximum effective upload limit is therefore 20 uploads per 3-hour window.
            </li>
            <li>
              <span className="text-text-primary font-medium">Guest uploads:</span> Videos submitted without a
              registered account cannot be linked to social media posts or saved to project history.
            </li>
          </ul>
          <p>
            Usage limits may change at any time with advance notice where reasonably practicable. You may not attempt
            to circumvent usage limits by any technical or other means.
          </p>
          <p>
            We reserve the right to impose additional limits, throttle access, or suspend accounts that consume
            resources in ways that degrade service quality for other users.
          </p>
        </Section>

        <Section number="Section 7" title="Your Content — Ownership and License">
          <p>
            <span className="text-text-primary font-medium">You own your content.</span> These Terms do not transfer
            ownership of any video, caption, image, or other material you submit (&quot;User Content&quot;).
          </p>
          <p>
            By uploading a video to the Service, you grant Surge a limited, non-exclusive, royalty-free license to
            transmit and process that video solely for the purpose of generating your craft analysis.{" "}
            <span className="text-text-primary font-medium">We do not retain your video.</span> Every uploaded video
            is transmitted to Google Gemini for analysis and permanently deleted from our servers within seconds of
            the analysis completing. No copy of your video remains on Surge&apos;s infrastructure after that point.
          </p>
          <p>
            By linking a social media post URL, you grant Surge a limited, non-exclusive, royalty-free license to
            read and store the public engagement metrics associated with that post for the purpose of tracking
            outcomes within your account.
          </p>
          <p>You represent and warrant that:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>You own or have all necessary rights and permissions to submit the User Content you provide;</li>
            <li>
              Your User Content does not infringe any third party&apos;s intellectual property, privacy, or other
              rights;
            </li>
            <li>
              Your User Content does not contain unlawful material, including material that violates child protection
              laws;
            </li>
            <li>
              You are authorized to link any social media post URL you provide, and doing so does not violate the
              terms of service of the relevant platform.
            </li>
          </ul>
          <p>
            You may delete your account at any time, which will remove all stored User Content data associated with
            your account. See our{" "}
            <Link href="/privacy" className="text-accent hover:underline">Privacy Policy</Link> for details.
          </p>
        </Section>

        <Section number="Section 8" title="Measurement Research Program">
          <p>
            The Measurement Research Program is an optional feature available exclusively to users who are (a) 18
            years of age or older, and (b) have explicitly opted in via Settings → Data &amp; Privacy.
          </p>
          <p>
            If you opt in, you grant Surge a non-exclusive license to use the public engagement data from your linked
            social media posts — including view counts, like counts, observation time, post URL, post age, and content
            niche — for internal measurement research and statistical analysis.{" "}
            <span className="text-text-primary font-medium">
              The Measurement Research Program never uses your video files.
            </span>{" "}
            Only publicly observable numeric metrics are used.
          </p>
          <p>You understand and agree that:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              Observed metrics are correlational data and are never treated as proof that a specific edit caused a
              particular outcome;
            </li>
            <li>
              Surge does not represent that participation in the Measurement Research Program will improve your
              content performance;
            </li>
            <li>
              Public engagement metrics may be influenced by factors outside your control, including purchased
              engagement, automated activity, platform algorithm changes, and other distortions;
            </li>
            <li>
              You may revoke consent and opt out at any time in Settings → Data &amp; Privacy, which will prevent
              future collection but will not delete already-collected observations;
            </li>
            <li>
              Users under 18 are permanently excluded from the Measurement Research Program and may not opt in
              regardless of account settings.
            </li>
          </ul>
        </Section>

        <Section number="Section 9" title="Acceptable Use Policy">
          <p>
            You agree to use the Service only for its intended purposes and in compliance with all applicable laws.
            You must not:
          </p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              <span className="text-text-primary font-medium">Automate or scrape:</span> Use any bot, script,
              crawler, or automated tool to access, scrape, index, or extract data from the Service;
            </li>
            <li>
              <span className="text-text-primary font-medium">Circumvent limits:</span> Attempt to bypass rate
              limits, upload limits, age verification, geographic restrictions, or any other technical controls;
            </li>
            <li>
              <span className="text-text-primary font-medium">Unauthorized access:</span> Probe, scan, or test the
              vulnerability of any Surge system or breach any security mechanism without express written permission;
            </li>
            <li>
              <span className="text-text-primary font-medium">Impersonation:</span> Create a false identity,
              impersonate any person or entity, or misrepresent your affiliation with any person or entity;
            </li>
            <li>
              <span className="text-text-primary font-medium">Content violations:</span> Submit content you do not
              have the right to submit, content that infringes intellectual property rights, content that contains
              malware, or content that depicts child sexual abuse material or other illegal content;
            </li>
            <li>
              <span className="text-text-primary font-medium">Interference:</span> Interfere with, disrupt, or
              attempt to gain unauthorized access to Surge&apos;s servers, networks, or systems;
            </li>
            <li>
              <span className="text-text-primary font-medium">Reverse engineering:</span> Reverse engineer,
              decompile, disassemble, or otherwise attempt to derive the source code of the Service or its AI models;
            </li>
            <li>
              <span className="text-text-primary font-medium">Resale:</span> Resell, sublicense, or commercially
              exploit the Service or its outputs without express written permission;
            </li>
            <li>
              <span className="text-text-primary font-medium">Misleading use:</span> Use the Service to generate or
              distribute misleading, deceptive, or fraudulent content;
            </li>
            <li>
              <span className="text-text-primary font-medium">Platform violations:</span> Use the Service in a manner
              that knowingly facilitates violations of TikTok&apos;s, Instagram&apos;s, or any other platform&apos;s
              terms of service;
            </li>
            <li>
              <span className="text-text-primary font-medium">Multiple accounts:</span> Create multiple accounts to
              circumvent restrictions, penalties, or usage limits applied to any single account.
            </li>
          </ul>
          <p>
            Violations may result in immediate suspension or termination of your account and may be referred to law
            enforcement authorities where appropriate.
          </p>
        </Section>

        <Section number="Section 10" title="AI-Generated Output Disclaimer">
          <p>
            The craft assessments, dimension scores, editing hypotheses, and experiment recommendations generated by
            Surge are produced by artificial intelligence (&quot;AI Output&quot;). You understand and agree that:
          </p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              AI Output represents subjective, AI-assisted craft opinions and editorial hypotheses, not objective
              measurements, scientific conclusions, or professional advice;
            </li>
            <li>
              Surge makes no representation or warranty that following AI Output will improve any content metric,
              including views, likes, watch time, follower count, or algorithmic distribution;
            </li>
            <li>AI Output is not a prediction, forecast, or guarantee of content performance on any platform;</li>
            <li>AI Output may contain errors, inaccuracies, or content that does not accurately reflect your video;</li>
            <li>
              Surge does not produce an aggregate &quot;viral score,&quot; virality index, or any composite
              performance prediction;
            </li>
            <li>
              The six retention craft dimensions are editorial dimensions, not retention or engagement measurements;
            </li>
            <li>
              Editing recommendations are hypotheses for your next controlled experiment, not proven optimization
              strategies.
            </li>
          </ul>
          <p>
            You are solely responsible for any decisions you make based on AI Output. We encourage you to treat AI
            Output as one input among many and to apply your own creative judgment.
          </p>
        </Section>

        <Section number="Section 11" title="Third-Party Services">
          <p>The Service integrates with the following third-party providers:</p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              <span className="text-text-primary font-medium">Google Gemini (Google LLC):</span> All uploaded videos
              are processed by Google&apos;s Gemini API. By using the Service, you acknowledge that your video is
              transmitted to Google and that Google&apos;s privacy policy and terms of service apply to that
              processing. Surge has no control over Google&apos;s data handling practices. You can review
              Google&apos;s policy at{" "}
              <a
                href="https://policies.google.com/privacy"
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                policies.google.com/privacy
              </a>.
            </li>
            <li>
              <span className="text-text-primary font-medium">TikWM and HikerAPI:</span> Public engagement metrics
              for linked posts are retrieved via third-party data providers including TikWM and HikerAPI. These
              providers are subject to their own availability, rate limits, and terms of service. Surge makes no
              guarantees regarding the accuracy, completeness, or timeliness of metrics retrieved via these
              providers. Metric retrieval may fail or be delayed due to provider outages, platform changes, or rate
              limiting.
            </li>
          </ul>
          <p>
            We are not responsible for the content, privacy practices, or terms of any third-party service. You are
            responsible for ensuring that your use of the Service does not violate TikTok&apos;s,
            Instagram&apos;s, or any other platform&apos;s terms of service.
          </p>
        </Section>

        <Section number="Section 12" title="Intellectual Property">
          <p>
            The Service, including its software, design, user interface, text, graphics, logos, and AI models
            (excluding User Content), is owned by Surge and protected by applicable copyright, trademark, trade
            secret, and other intellectual property laws.
          </p>
          <p>
            We grant you a limited, non-exclusive, non-transferable, revocable license to access and use the Service
            solely for your personal, non-commercial use in accordance with these Terms. This license does not
            include any right to sublicense, sell, or commercially exploit the Service; modify or create derivative
            works; use data mining or extraction methods on the Service; or use Surge&apos;s name, logo, or branding
            without our express written permission.
          </p>
          <p>
            <span className="text-text-primary font-medium">DMCA Notice:</span> If you believe that content on the
            Service infringes your copyright, please send a notice to{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>{" "}
            containing: (a) your contact information; (b) identification of the copyrighted work claimed to be
            infringed; (c) identification of the infringing material and its location; (d) a statement of good faith
            belief that the use is not authorized; and (e) a statement under penalty of perjury that you are
            authorized to act on behalf of the copyright owner.
          </p>
        </Section>

        <Section number="Section 13" title="Disclaimer of Warranties">
          <CapsBlock>
            THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot; WITHOUT WARRANTIES OF ANY KIND,
            EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS
            FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT. SURGE DOES NOT WARRANT THAT (A) THE SERVICE WILL
            BE UNINTERRUPTED, ERROR-FREE, OR SECURE; (B) ANY DEFECTS WILL BE CORRECTED; (C) THE SERVICE OR THE
            SERVERS THAT MAKE IT AVAILABLE ARE FREE OF VIRUSES OR OTHER HARMFUL COMPONENTS; OR (D) ANY AI OUTPUT
            WILL BE ACCURATE, COMPLETE, RELIABLE, OR SUITABLE FOR ANY PURPOSE.
          </CapsBlock>
          <p>
            Craft assessments, dimension scores, observed metrics, and experiment recommendations are informational
            only and come with no warranty of accuracy or fitness for any editorial or commercial goal.
          </p>
          <p>
            Social media platform metrics retrieved via third-party providers are not independently verified and may
            differ from metrics shown natively within those platforms. Surge is not responsible for discrepancies.
          </p>
        </Section>

        <Section number="Section 14" title="Limitation of Liability">
          <CapsBlock>
            TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL SURGE, ITS OPERATORS, EMPLOYEES,
            AGENTS, OR LICENSORS BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, OR
            PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS, LOSS OF DATA, LOSS OF GOODWILL,
            BUSINESS INTERRUPTION, COST OF SUBSTITUTE SERVICES, OR DAMAGES RESULTING FROM: (A) YOUR USE OF OR
            INABILITY TO USE THE SERVICE; (B) ANY AI OUTPUT OR RECOMMENDATION; (C) UNAUTHORIZED ACCESS TO OR
            ALTERATION OF YOUR TRANSMISSIONS OR DATA; (D) CONDUCT OF ANY THIRD PARTY ON THE SERVICE; OR (E) ANY
            OTHER MATTER RELATING TO THE SERVICE.
          </CapsBlock>
          <CapsBlock>
            SURGE&apos;S TOTAL CUMULATIVE LIABILITY TO YOU FOR ALL CLAIMS ARISING OUT OF OR RELATED TO THESE TERMS
            OR THE SERVICE SHALL NOT EXCEED THE GREATER OF (A) THE TOTAL AMOUNT YOU PAID TO SURGE IN THE SIX (6)
            MONTHS IMMEDIATELY PRECEDING THE CLAIM, OR (B) FIFTY U.S. DOLLARS ($50.00).
          </CapsBlock>
          <p>
            Some jurisdictions do not allow the exclusion or limitation of certain damages, so some of the above
            limitations may not apply to you.
          </p>
        </Section>

        <Section number="Section 15" title="Indemnification">
          <p>
            You agree to defend, indemnify, and hold harmless Surge and its operators, employees, agents, and
            licensors from and against any claims, liabilities, damages, losses, and expenses, including reasonable
            attorneys&apos; fees, arising out of or in any way connected with:
          </p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>Your access to or use of the Service;</li>
            <li>
              Your User Content, including any claim that your User Content infringes, misappropriates, or violates
              any third-party right;
            </li>
            <li>Your violation of these Terms;</li>
            <li>Your violation of any applicable law or regulation;</li>
            <li>
              Your violation of any third-party platform&apos;s terms of service in connection with your use of the
              Service.
            </li>
          </ul>
          <p>
            We reserve the right to assume exclusive defense and control of any matter subject to indemnification by
            you, in which case you agree to cooperate with our defense of such claim.
          </p>
        </Section>

        <Section number="Section 16" title="Termination">
          <p>
            <span className="text-text-primary font-medium">Termination by you:</span> You may stop using the
            Service at any time and may request deletion of your account by emailing{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>. Upon account deletion, we will remove your account data in accordance with our Privacy Policy.
          </p>
          <p>
            <span className="text-text-primary font-medium">Termination by Surge:</span> We may suspend or terminate
            your account and access to the Service at any time, with or without cause and with or without notice,
            including if we reasonably believe you have violated these Terms, engaged in fraudulent or illegal
            activity, or if your actions harm other users or Surge.
          </p>
          <p>
            <span className="text-text-primary font-medium">Effect of termination:</span> Upon termination, your
            right to use the Service immediately ceases. Sections 7, 10, 12, 13, 14, 15, 17, and 18 survive
            termination of these Terms for any reason.
          </p>
          <p>
            We are not liable to you or any third party for any termination of your access to the Service.
          </p>
        </Section>

        <Section number="Section 17" title="Dispute Resolution and Arbitration">
          <div className="bg-surface border border-border rounded-lg px-4 py-3 text-xs text-text-muted leading-relaxed mb-1">
            <span className="text-text-primary font-medium">Please read this section carefully.</span> It affects
            your legal rights, including your right to file a lawsuit in court and your right to a jury trial.
          </div>
          <p>
            <span className="text-text-primary font-medium">Informal resolution:</span> Before filing any formal
            legal claim, you agree to first contact us at{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>{" "}
            with a written description of your dispute. We will attempt to resolve it informally within 30 days.
          </p>
          <p>
            <span className="text-text-primary font-medium">Binding arbitration:</span> Except for disputes that
            qualify for small claims court, you and Surge agree that any dispute, claim, or controversy arising out
            of or relating to these Terms or the Service shall be resolved by binding individual arbitration
            administered by the American Arbitration Association (&quot;AAA&quot;) under its Consumer Arbitration
            Rules. The arbitration will be conducted in English, in Texas. Judgment on the award may be entered in
            any court of competent jurisdiction.
          </p>
          <p>
            <span className="text-text-primary font-medium">Class action waiver:</span>{" "}
            <span className="text-text-primary font-medium">
              You and Surge each waive any right to participate in a class action lawsuit, class-wide arbitration,
              or any other representative proceeding.
            </span>{" "}
            All disputes must be brought in your individual capacity.
          </p>
          <p>
            <span className="text-text-primary font-medium">Exceptions:</span> Either party may bring an individual
            action in small claims court, or seek emergency injunctive or equitable relief from a court of competent
            jurisdiction to prevent actual or threatened infringement of intellectual property rights.
          </p>
          <p>
            <span className="text-text-primary font-medium">Opt-out:</span> You may opt out of the arbitration
            agreement within 30 days of first agreeing to these Terms by emailing{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a>{" "}
            with the subject line &quot;Arbitration Opt-Out&quot; and your name and account email address.
          </p>
        </Section>

        <Section number="Section 18" title="Governing Law and Venue">
          <p>
            These Terms are governed by and construed in accordance with the laws of the State of Texas, without
            regard to its conflict of law provisions.
          </p>
          <p>
            For any disputes not subject to arbitration under Section 17, you and Surge consent to the exclusive
            jurisdiction of the state and federal courts located in Texas, and you waive any objection to
            jurisdiction or venue in those courts.
          </p>
        </Section>

        <Section number="Section 19" title="General Provisions">
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              <span className="text-text-primary font-medium">Entire agreement:</span> These Terms, together with
              our Privacy Policy, constitute the entire agreement between you and Surge regarding the Service and
              supersede all prior agreements or communications on this subject.
            </li>
            <li>
              <span className="text-text-primary font-medium">Severability:</span> If any provision of these Terms
              is found to be unenforceable or invalid, that provision will be limited or eliminated to the minimum
              extent necessary so that the remaining Terms continue in full force and effect.
            </li>
            <li>
              <span className="text-text-primary font-medium">Waiver:</span> Our failure to enforce any right or
              provision of these Terms does not constitute a waiver of that right or provision. Any waiver must be
              in writing and signed by an authorized representative of Surge.
            </li>
            <li>
              <span className="text-text-primary font-medium">Assignment:</span> You may not assign or transfer your
              rights or obligations under these Terms without our prior written consent. We may assign these Terms
              without restriction, including in connection with a merger, acquisition, or sale of assets.
            </li>
            <li>
              <span className="text-text-primary font-medium">No third-party beneficiaries:</span> These Terms do
              not create any third-party beneficiary rights.
            </li>
            <li>
              <span className="text-text-primary font-medium">Force majeure:</span> We are not liable for delays or
              failures in performance resulting from causes beyond our reasonable control, including natural
              disasters, government actions, internet service disruptions, or acts of third parties.
            </li>
            <li>
              <span className="text-text-primary font-medium">Notices:</span> Notices to Surge must be sent by email
              to{" "}
              <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
                surgeprivacy@gmail.com
              </a>. We may give notice to you via email to the address associated with your account or via a
              prominent notice on the Service.
            </li>
            <li>
              <span className="text-text-primary font-medium">Language:</span> These Terms were written in English.
              In the event of any conflict between an English version and a translated version, the English version
              controls.
            </li>
          </ul>
        </Section>

        <Section number="Section 20" title="Contact Information">
          <p>
            For questions about these Terms, privacy requests, DMCA notices, account deletion, or general support,
            please contact:
          </p>
          <p className="text-text-primary">
            Surge<br />
            Email:{" "}
            <a href="mailto:surgeprivacy@gmail.com" className="text-accent hover:underline">
              surgeprivacy@gmail.com
            </a><br />
            Website:{" "}
            <a
              href={SITE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              {SITE_HOST}
            </a>
          </p>
          <p>
            For privacy-specific requests (data access, deletion, CCPA), please reference our{" "}
            <Link href="/privacy" className="text-accent hover:underline">Privacy Policy</Link>.
          </p>
        </Section>

        <div className="border-t border-border pt-6 text-xs text-text-muted text-center space-y-1">
          <p>Surge Terms of Service &nbsp;·&nbsp; Effective June 26, 2026</p>
          <p>
            See also our{" "}
            <Link href="/privacy" className="text-accent hover:underline">Privacy Policy</Link>.
          </p>
        </div>
      </div>
    </main>
  );
}
