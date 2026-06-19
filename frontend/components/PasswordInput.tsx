"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

interface Props {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  required?: boolean;
  autoComplete?: string;
  autoFocus?: boolean;
  className?: string;
}

const DEFAULT_CLASS =
  "w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to";

export default function PasswordInput({
  value,
  onChange,
  placeholder,
  required,
  autoComplete,
  autoFocus,
  className = DEFAULT_CLASS,
}: Props) {
  const [visible, setVisible] = useState(false);

  // Swap px-4 → pl-4 so the explicit pr-10 below doesn't fight the shorthand
  const inputClass = className.replace("px-4", "pl-4") + " pr-10";

  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        className={inputClass}
      />
      <button
        type="button"
        tabIndex={-1}
        aria-label={visible ? "Hide password" : "Show password"}
        onClick={() => setVisible((v) => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
      >
        {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  );
}
