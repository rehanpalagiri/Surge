"use client";

import { useEffect, useRef } from "react";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
const GSI_SRC = "https://accounts.google.com/gsi/client";

/** True only when a Google OAuth client ID is configured. Lets callers hide
 * surrounding chrome (e.g. an "or" divider) so nothing orphans when it's unset. */
export const GOOGLE_ENABLED = !!CLIENT_ID;

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    google?: any;
  }
}

/**
 * Renders the official "Sign in with Google" button via Google Identity
 * Services. On success it hands the ID-token credential back to the caller,
 * which exchanges it at /api/auth/google. Renders nothing until
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID is set, so it's a no-op before OAuth is configured.
 */
export default function GoogleSignInButton({
  onCredential,
  text = "signup_with",
}: {
  onCredential: (credential: string) => void;
  text?: "signin_with" | "signup_with" | "continue_with";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cbRef = useRef(onCredential);
  cbRef.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) return;

    function render() {
      if (!window.google || !ref.current) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: (resp: { credential?: string }) => {
          if (resp?.credential) cbRef.current(resp.credential);
        },
      });
      ref.current.innerHTML = "";
      window.google.accounts.id.renderButton(ref.current, {
        theme: "filled_black",
        size: "large",
        width: 320,
        text,
        shape: "pill",
      });
    }

    if (window.google) {
      render();
      return;
    }
    let script = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener("load", render);
    return () => script?.removeEventListener("load", render);
  }, [text]);

  if (!CLIENT_ID) return null;
  return <div ref={ref} className="flex justify-center" />;
}
