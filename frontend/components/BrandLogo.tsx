import Link from "next/link";

type BrandLogoProps = {
  className?: string;
  href?: string | null;
  ariaLabel?: string;
};

/** The canonical CraftLint wordmark used everywhere in the product. */
export default function BrandLogo({
  className = "",
  href = "/",
  ariaLabel = "CraftLint home",
}: BrandLogoProps) {
  const classes = `surge-wordmark ${className}`.trim();

  if (!href) return <span className={classes}>CraftLint</span>;

  return (
    <Link href={href} className={classes} aria-label={ariaLabel}>
      CraftLint
    </Link>
  );
}
