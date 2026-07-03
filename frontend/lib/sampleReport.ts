// Static example review shown on /sample and (in miniature) on the guest
// landing page. Kept honest: the numbers are from a hand-written example,
// and every surface that renders them says so.

export const SAMPLE_REPORT = {
  niche: "Fitness",
  platform: "tiktok" as const,
  mode: "Outcome-blind craft review",
  verdict: "Strong craft" as const,
  hook_velocity: 9,
  cut_frequency: 7,
  text_scannability: 6,
  curiosity_gap: 8,
  audio_visual_sync: 8,
  loop_seamlessness: 4,
  strengths: [
    "Hook velocity is exceptional — transformation cut lands on frame 1 with bold text overlay, eliminating the viewer's reason to scroll before they consciously decide to.",
    "Curiosity gap is strong: opening line 'Most people train wrong for years and never know it' creates an immediate open loop that demands resolution.",
    "Audio-visual sync is tight throughout — every major cut lands on a beat drop or audio transient, making the pacing feel intentional and professional.",
  ],
  improvements: [
    "The ending clearly signals completion. Testing a callback to the opening could make the structure feel more cohesive.",
    "Text scannability drops at 0:08–0:14 — caption overlay appears in the bottom 20% of frame and will be covered by TikTok's description UI on most devices.",
    "Cut frequency sags at 0:12–0:18 — a 4.2-second static talking-head shot after the hook loses the attention the opening earned.",
  ],
  analysis_summary:
    "The opening communicates its premise quickly and creates a clear unanswered question. The ending does not connect back to that opening, and the middle contains a long static section. Test a callback ending and a tighter middle, then compare real viewer response after posting.",
  improvement_plan: [
    {
      priority: "High",
      action: "Strengthen the ending",
      detail:
        "Test removing the generic sign-off and ending with a visual or thematic callback to the opening. Treat this as an editing hypothesis, then compare fixed-age outcomes.",
    },
    {
      priority: "High",
      action: "Move text out of the UI collision zone",
      detail:
        "At 0:08–0:14, your caption text sits in the bottom 20% of frame. On most devices, TikTok's username and description overlay will cover it entirely. Move all on-screen text to the center or upper third of the frame.",
    },
    {
      priority: "Medium",
      action: "Cut the 0:12–0:18 static hold",
      detail:
        "You hold a talking-head shot for 4.2 seconds with no visual change. Test a subtle zoom or relevant B-roll and compare viewer response.",
    },
  ],
};

export const SAMPLE_SCORES = [
  { label: "Hook Velocity",     score: SAMPLE_REPORT.hook_velocity },
  { label: "Cut Frequency",     score: SAMPLE_REPORT.cut_frequency },
  { label: "Text Scannability", score: SAMPLE_REPORT.text_scannability },
  { label: "Curiosity Gap",     score: SAMPLE_REPORT.curiosity_gap },
  { label: "Audio-Visual Sync", score: SAMPLE_REPORT.audio_visual_sync },
  { label: "Ending Strength",   score: SAMPLE_REPORT.loop_seamlessness },
];

/** One risk-map entry for the landing miniature. */
export const SAMPLE_RISK = {
  section: "0:08–0:14",
  risk: "high" as const,
  reason:
    "Caption text sits in the bottom 20% of frame — TikTok's description UI covers it on most devices.",
};
