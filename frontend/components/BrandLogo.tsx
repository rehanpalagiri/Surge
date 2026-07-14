import Link from "next/link";

type BrandLogoProps = {
  className?: string;
  href?: string | null;
  ariaLabel?: string;
};

/** The canonical Surge wordmark used everywhere in the product. */
export default function BrandLogo({
  className = "",
  href = "/",
  ariaLabel = "Surge home",
}: BrandLogoProps) {
  const classes = `surge-wordmark ${className}`.trim();

  if (!href) return <span className={classes}>Surge</span>;

  return (
    <Link href={href} className={classes} aria-label={ariaLabel}>
      Surge
    </Link>
  );
}
