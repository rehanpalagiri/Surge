// Single source of truth for rendering craft verdicts.
//
// Backend verdict strings are stable API/data values ("Strong craft",
// "Developing craft", "Needs revision", legacy "High/Average/Low potential",
// "Needs work", "Error"). We soften only the DISPLAY: the bottom rung reads
// as a craft ladder ("Early craft"), in terracotta rather than alarm red —
// a low score is an editing observation, not a failure notice.

export type VerdictTone = "strong" | "developing" | "early" | "error";

export interface VerdictDisplay {
  label: string;
  tone: VerdictTone;
  /** Text color for the verdict word itself. */
  textClass: string;
  /** Wash + border for banner-style surfaces. */
  bannerClass: string;
}

const STRONG = new Set(["Strong craft", "High potential"]);
const DEVELOPING = new Set(["Developing craft", "Average potential"]);

export function verdictDisplay(verdict: string): VerdictDisplay {
  if (STRONG.has(verdict)) {
    return {
      label: "Strong craft",
      tone: "strong",
      textClass: "text-success",
      bannerClass: "bg-success/10 border-success/30",
    };
  }
  if (DEVELOPING.has(verdict)) {
    return {
      label: "Developing craft",
      tone: "developing",
      textClass: "text-warning",
      bannerClass: "bg-warning/10 border-warning/30",
    };
  }
  if (verdict === "Error") {
    return {
      label: "Analysis failed",
      tone: "error",
      textClass: "text-text-muted",
      bannerClass: "bg-surface border-border",
    };
  }
  // "Needs revision", legacy "Needs work" / "Low potential", and anything else.
  return {
    label: "Early craft",
    tone: "early",
    textClass: "text-accent",
    bannerClass: "bg-accent/10 border-accent/30",
  };
}
