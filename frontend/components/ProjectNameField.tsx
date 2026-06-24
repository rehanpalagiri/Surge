"use client";

import { FolderPen } from "lucide-react";

interface ProjectNameFieldProps {
  value: string;
  onChange: (value: string) => void;
  isUpdate?: boolean;
}

export default function ProjectNameField({ value, onChange, isUpdate = false }: ProjectNameFieldProps) {
  return (
    <div className="space-y-2 text-left">
      <div className="flex items-end justify-between gap-3">
        <div>
          <label htmlFor="project-name" className="block text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Project name
          </label>
          <p className="mt-0.5 text-xs text-zinc-600">
            {isUpdate ? "Keep the same name or rename this update." : "Give this video a name you will recognize later."}
          </p>
        </div>
        <span className="text-[11px] tabular-nums text-zinc-600">{value.length}/80</span>
      </div>
      <div className="group relative">
        <FolderPen
          className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-zinc-500 transition-colors group-focus-within:text-purple-400"
          strokeWidth={1.6}
        />
        <input
          id="project-name"
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          maxLength={80}
          required
          autoComplete="off"
          placeholder="e.g. Summer launch hook test"
          className="w-full rounded-xl border border-zinc-700 bg-zinc-900 py-3.5 pl-12 pr-4 text-sm font-medium text-white placeholder:text-zinc-600 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
        />
      </div>
    </div>
  );
}

