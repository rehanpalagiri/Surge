// Cinematic creator silhouette used inside the landing "video" surfaces
// (the hero craft-review frame and the "CraftLint reads the edit" scan card).
// Rendered as a single self-contained SVG so it stays crisp at any size and
// theme-aware via CSS tokens. It reads as a real short-form video still:
// a ring-lit portrait with a pink key-light tracing the figure (pink = the
// "live / act" signal in the Noir system) — never a placeholder blob.
//
// The two landing surfaces it sits on are deliberately dark "video islands"
// in BOTH themes, so the silhouette + lighting are tuned for a dark backdrop.

// Contour shared by the fill and the rim-light stroke (head → neck → shoulders).
const LEFT_EDGE =
  "M6 340C6 250 34 214 94 200C100 182 100 170 100 158C76 152 68 122 68 106C68 66 92 44 120 44";

const SILHOUETTE = `${LEFT_EDGE}C148 44 172 66 172 106C172 122 164 152 140 158C140 170 140 182 146 200C206 214 234 250 234 340Z`;

export default function CreatorFigure({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 240 340"
      role="img"
      aria-label="Creator on camera"
      preserveAspectRatio="xMidYMax meet"
    >
      <defs>
        {/* Soft studio back-glow pooling behind the head. */}
        <radialGradient id="cf-pool" cx="50%" cy="34%" r="52%">
          <stop offset="0%" stopColor="#E7ECF6" stopOpacity="0.16" />
          <stop offset="55%" stopColor="#E7ECF6" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#E7ECF6" stopOpacity="0" />
        </radialGradient>
        {/* Subtle form modelling on the figure — front plane lifts, edges fall off. */}
        <linearGradient id="cf-body" x1="26%" y1="10%" x2="78%" y2="96%">
          <stop offset="0%" stopColor="#26252C" />
          <stop offset="46%" stopColor="#191820" />
          <stop offset="100%" stopColor="#0E0D12" />
        </linearGradient>
        {/* Cool fill-light kissing the camera-right edge (ice = the "inform" tone). */}
        <linearGradient id="cf-fill" x1="100%" y1="0%" x2="0%" y2="0%">
          <stop offset="0%" stopColor="#8CD0FF" stopOpacity="0.5" />
          <stop offset="34%" stopColor="#8CD0FF" stopOpacity="0" />
        </linearGradient>
        <filter id="cf-soft" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="3.4" />
        </filter>
        <filter id="cf-halo" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="1.6" />
        </filter>
        <clipPath id="cf-clip">
          <path d={SILHOUETTE} />
        </clipPath>
      </defs>

      {/* Studio back-glow. */}
      <rect x="0" y="0" width="240" height="340" fill="url(#cf-pool)" />

      {/* Ring-light halo — the tell that this is a creator on camera. */}
      <circle
        cx="120"
        cy="104"
        r="78"
        fill="none"
        stroke="#DCE4F2"
        strokeOpacity="0.28"
        strokeWidth="1.4"
        filter="url(#cf-halo)"
      />
      <circle cx="120" cy="104" r="78" fill="none" stroke="#DCE4F2" strokeOpacity="0.12" strokeWidth="0.7" />

      {/* Figure body. */}
      <path d={SILHOUETTE} fill="url(#cf-body)" />

      {/* Interior lights, clipped to the body so nothing spills. */}
      <g clipPath="url(#cf-clip)">
        {/* cool fill on the right cheek / shoulder */}
        <rect x="0" y="0" width="240" height="340" fill="url(#cf-fill)" />
        {/* warm top-light catching the crown */}
        <ellipse cx="112" cy="70" rx="58" ry="46" fill="#3A3944" opacity="0.55" filter="url(#cf-soft)" />
        {/* neck shadow to separate head from shoulders */}
        <ellipse cx="120" cy="176" rx="30" ry="16" fill="#000" opacity="0.35" filter="url(#cf-soft)" />
      </g>

      {/* Pink key/rim light along the camera-left contour — soft under, crisp over. */}
      <path
        d={LEFT_EDGE}
        fill="none"
        stroke="var(--color-accent, #FF4D8D)"
        strokeWidth="7"
        strokeLinecap="round"
        opacity="0.32"
        filter="url(#cf-soft)"
      />
      <path
        d={LEFT_EDGE}
        fill="none"
        stroke="var(--color-accent, #FF4D8D)"
        strokeWidth="2.4"
        strokeLinecap="round"
        opacity="0.92"
      />
      {/* Catch-light where the rim meets the shoulder. */}
      <circle cx="94" cy="200" r="2.6" fill="#FFE1EC" opacity="0.9" />
    </svg>
  );
}
