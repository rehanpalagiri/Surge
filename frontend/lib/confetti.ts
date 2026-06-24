// Lightweight, dependency-free confetti burst. Appends a transient full-screen
// canvas, animates a particle burst, then removes itself. No-ops on the server
// and for users who prefer reduced motion.
const CONFETTI_COLORS = ["#7c3aed", "#a855f7", "#2563eb", "#3b82f6", "#22c55e", "#eab308"];

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  rot: number;
  vr: number;
  w: number;
  h: number;
  color: string;
}

export function fireConfetti() {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

  const canvas = document.createElement("canvas");
  canvas.style.cssText =
    "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9999";
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    canvas.remove();
    return;
  }

  const count = 150;
  const particles: Particle[] = [];
  const originX = canvas.width / 2;
  const originY = canvas.height * 0.3;
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + Math.random();
    const speed = 6 + Math.random() * 9;
    particles.push({
      x: originX,
      y: originY,
      vx: Math.cos(angle) * speed * (0.4 + Math.random()),
      vy: Math.sin(angle) * speed - (5 + Math.random() * 6),
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.32,
      w: 6 + Math.random() * 6,
      h: 9 + Math.random() * 9,
      color: CONFETTI_COLORS[(Math.random() * CONFETTI_COLORS.length) | 0],
    });
  }

  const gravity = 0.34;
  const duration = 2800;
  const start = performance.now();

  function frame(now: number) {
    const elapsed = now - start;
    ctx!.clearRect(0, 0, canvas.width, canvas.height);
    const fade = elapsed > duration - 700 ? Math.max(0, (duration - elapsed) / 700) : 1;

    for (const p of particles) {
      p.vy += gravity;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vr;
      ctx!.save();
      ctx!.globalAlpha = fade;
      ctx!.translate(p.x, p.y);
      ctx!.rotate(p.rot);
      ctx!.fillStyle = p.color;
      ctx!.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx!.restore();
    }

    if (elapsed < duration) {
      requestAnimationFrame(frame);
    } else {
      canvas.remove();
    }
  }

  requestAnimationFrame(frame);
}
