import type { HTMLAttributes, ReactNode } from "react";

type SkeletonProps = HTMLAttributes<HTMLDivElement> & {
  width?: string;
  height?: string;
};

export function Skeleton({ className = "", width, height, style, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`skeleton ${className}`}
      style={{ width, height, ...style }}
      {...props}
    />
  );
}

export function SkeletonText({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={`space-y-2.5 ${className}`}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className="h-3.5 rounded-md" width={index === lines - 1 ? "68%" : "100%"} />
      ))}
    </div>
  );
}

export function SkeletonTitle({ className = "", width = "52%" }: { className?: string; width?: string }) {
  return <Skeleton className={`h-7 rounded-lg ${className}`} width={width} />;
}

export function SkeletonAvatar({ className = "" }: { className?: string }) {
  return <Skeleton className={`h-11 w-11 shrink-0 rounded-full ${className}`} />;
}

export function SkeletonButton({ className = "" }: { className?: string }) {
  return <Skeleton className={`h-11 w-36 rounded-xl ${className}`} />;
}

export function SkeletonInput({ className = "" }: { className?: string }) {
  return <Skeleton className={`h-12 w-full rounded-xl ${className}`} />;
}

export function SkeletonCard({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <div aria-hidden="true" className={`rounded-2xl border border-border bg-card p-5 sm:p-6 ${className}`}>
      {children}
    </div>
  );
}

export function SkeletonReportSection({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <SkeletonCard className={`space-y-4 ${className}`}>{children ?? <><SkeletonTitle width="38%" className="h-5" /><SkeletonText lines={3} /></>}</SkeletonCard>;
}

export function SkeletonProjectRow() {
  return (
    <SkeletonCard className="min-h-52 space-y-4">
      <SkeletonTitle width="42%" className="h-5" />
      <SkeletonText lines={2} />
      <div className="flex gap-2 pt-2"><Skeleton className="h-8 w-24 rounded-lg" /><Skeleton className="h-8 w-36 rounded-lg" /></div>
    </SkeletonCard>
  );
}

export function SkeletonScoreRow() {
  return (
    <div aria-hidden="true" className="grid grid-cols-[minmax(0,1fr)_7rem] items-center gap-4 py-2">
      <Skeleton className="h-4 rounded-md" width="72%" />
      <div className="flex items-center gap-2">
        <Skeleton className="h-2 flex-1 rounded-full" />
        <Skeleton className="h-4 w-6 rounded-md" />
      </div>
    </div>
  );
}

export function SkeletonFormSection({ fields = 3 }: { fields?: number }) {
  return (
    <SkeletonCard className="space-y-5">
      <div className="space-y-2">
        <SkeletonTitle width="38%" className="h-5" />
        <Skeleton className="h-3 rounded-md" width="66%" />
      </div>
      {Array.from({ length: fields }, (_, index) => (
        <div key={index} className="space-y-2">
          <Skeleton className="h-3 w-24 rounded-md" />
          <SkeletonInput />
        </div>
      ))}
      <SkeletonButton />
    </SkeletonCard>
  );
}

export function SkeletonMedia({ className = "" }: { className?: string }) {
  return <Skeleton className={`aspect-video w-full rounded-2xl ${className}`} />;
}

export function LandingSkeleton() {
  return (
    <main className="surge-skeleton min-h-screen bg-background" aria-busy="true" aria-label="Loading CraftLint">
      <header className="surge-skeleton-nav">
        <Skeleton className="h-8 w-28 rounded-lg" />
        <Skeleton className="h-9 w-24 rounded-lg" />
      </header>
      <section className="surge-skeleton-hero">
        <div className="space-y-5">
          <Skeleton className="h-3 w-44 rounded-md" />
          <Skeleton className="h-16 w-full max-w-xl rounded-xl" />
          <Skeleton className="h-4 w-10/12 rounded-md" />
          <Skeleton className="h-12 w-44 rounded-xl" />
        </div>
        <Skeleton className="aspect-[1.35] w-full rounded-2xl" />
      </section>
      <section className="surge-skeleton-upload">
        <SkeletonTitle width="45%" className="mx-auto" />
        <Skeleton className="h-64 w-full rounded-2xl" />
        <SkeletonButton className="w-full" />
      </section>
    </main>
  );
}

export function LoadingRegion({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={`skeleton-delay ${className}`} aria-busy="true" aria-label={label}>
      <span className="sr-only" role="status">{label}</span>
      {children}
    </section>
  );
}

export function ReportSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <LoadingRegion label="Loading craft review" className={`w-full ${compact ? "max-w-3xl" : "max-w-4xl"} mx-auto space-y-5`}>
      <SkeletonCard className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-2 flex-1">
            <Skeleton className="h-3 w-28 rounded-md" />
            <SkeletonTitle width="58%" />
          </div>
          <SkeletonAvatar className="h-14 w-14" />
        </div>
        <SkeletonText lines={2} />
      </SkeletonCard>
      <div className="grid gap-5 md:grid-cols-2">
        <SkeletonCard>
          <SkeletonTitle width="46%" className="h-5 mb-4" />
          <div className="divide-y divide-border">
            {Array.from({ length: compact ? 4 : 6 }, (_, index) => <SkeletonScoreRow key={index} />)}
          </div>
        </SkeletonCard>
        <SkeletonCard className="space-y-4">
          <SkeletonTitle width="42%" className="h-5" />
          <SkeletonMedia />
          <SkeletonText lines={2} />
        </SkeletonCard>
      </div>
      {!compact && (
        <SkeletonCard className="space-y-4">
          <SkeletonTitle width="34%" className="h-5" />
          <div className="grid gap-3 sm:grid-cols-3">
            {[0, 1, 2].map((item) => <Skeleton key={item} className="h-24 rounded-xl" />)}
          </div>
        </SkeletonCard>
      )}
    </LoadingRegion>
  );
}

export function ImproveSkeleton() {
  return (
    <LoadingRegion label="Loading improvement report" className="max-w-3xl mx-auto space-y-5">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-3 w-24 rounded-md" />
        <SkeletonTitle width="62%" />
        <Skeleton className="h-4 rounded-md" width="78%" />
      </div>
      {[0, 1, 2].map((item) => (
        <SkeletonCard key={item} className="space-y-4">
          <div className="flex items-center gap-3"><SkeletonAvatar /><SkeletonTitle width="38%" className="h-5" /></div>
          <SkeletonText lines={3} />
          <Skeleton className="h-9 w-28 rounded-lg" />
        </SkeletonCard>
      ))}
    </LoadingRegion>
  );
}

export function ProjectsSkeleton() {
  return (
    <LoadingRegion label="Loading project history" className="space-y-4">
      <Skeleton className="h-3 w-20 rounded-md" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {[0, 1, 2, 3].map((item) => <SkeletonProjectRow key={item} />)}
      </div>
    </LoadingRegion>
  );
}

export function ProfileSkeleton() {
  return <LoadingRegion label="Loading creator profiles"><SkeletonFormSection fields={4} /></LoadingRegion>;
}

export function SettingsPrivacySkeleton() {
  return (
    <LoadingRegion label="Loading privacy settings" className="space-y-2">
      {[0, 1, 2].map((item) => <Skeleton key={item} className="h-14 w-full rounded-xl" />)}
    </LoadingRegion>
  );
}

export function SettingsSkeleton() {
  return (
    <LoadingRegion label="Loading settings" className="space-y-5">
      <SkeletonFormSection fields={2} />
      <SkeletonFormSection fields={2} />
      <SkeletonCard className="space-y-3">
        <SkeletonTitle width="34%" className="h-5" />
        <SettingsPrivacySkeleton />
      </SkeletonCard>
    </LoadingRegion>
  );
}

export function AdminDataSkeleton() {
  return (
    <LoadingRegion label="Loading admin data" className="space-y-3">
      {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-16 w-full rounded-xl" />)}
    </LoadingRegion>
  );
}
