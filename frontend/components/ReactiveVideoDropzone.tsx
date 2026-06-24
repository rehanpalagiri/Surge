"use client";

import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import { CheckCircle2, FileVideo2, Sparkles, UploadCloud } from "lucide-react";

interface ReactiveVideoDropzoneProps {
  file: File | null;
  onFileSelected: (file: File) => void | Promise<void>;
  selectedDetail?: ReactNode;
  idleNote?: string;
  disabled?: boolean;
}

type DropzoneStyle = CSSProperties & {
  "--drop-x"?: string;
  "--drop-y"?: string;
};

export default function ReactiveVideoDropzone({
  file,
  onFileSelected,
  selectedDetail,
  idleNote = "Your video stays private and is deleted after review",
  disabled = false,
}: ReactiveVideoDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  const receiveFile = (selected?: File) => {
    if (selected && !disabled) void onFileSelected(selected);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--drop-x", `${event.clientX - rect.left}px`);
    event.currentTarget.style.setProperty("--drop-y", `${event.clientY - rect.top}px`);
  };

  const handleDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (disabled) return;
    dragDepth.current += 1;
    setDragging(true);
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    receiveFile(event.dataTransfer.files[0]);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-label={file ? `Change selected video: ${file.name}` : "Choose or drop a video to analyze"}
      onClick={openPicker}
      onKeyDown={handleKeyDown}
      onPointerMove={handlePointerMove}
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`reactive-dropzone group ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""} ${disabled ? "is-disabled" : ""}`}
      style={{ "--drop-x": "50%", "--drop-y": "50%" } as DropzoneStyle}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        onChange={(event) => {
          const selected = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          receiveFile(selected);
        }}
      />

      <div className="dropzone-grid" aria-hidden="true" />
      <div className="dropzone-scan" aria-hidden="true" />

      {dragging ? (
        <div className="relative z-10 flex flex-col items-center gap-4 text-center motion-pop">
          <div className="dropzone-icon-shell is-active">
            <UploadCloud className="h-9 w-9" strokeWidth={1.6} />
          </div>
          <div>
            <p className="text-lg font-bold text-white">Release to add your video</p>
            <p className="mt-1 text-sm text-purple-200/70">We&apos;ll validate it immediately</p>
          </div>
        </div>
      ) : file ? (
        <div className="relative z-10 w-full max-w-lg motion-pop">
          <div className="mb-4 flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
              <CheckCircle2 className="h-3.5 w-3.5" /> Ready
            </span>
            <span className="text-xs text-zinc-500">Tap anywhere to replace</span>
          </div>

          <div className="flex items-center gap-4 text-left">
            <div className="dropzone-file-icon">
              <FileVideo2 className="h-7 w-7" strokeWidth={1.6} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-semibold text-white">{file.name}</p>
              <div className="mt-1 text-xs text-zinc-400">{selectedDetail}</div>
            </div>
          </div>

          <div className="dropzone-ready-track mt-5" aria-hidden="true">
            <div className="dropzone-ready-fill" />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px]">
            <span className="text-zinc-500">File checked</span>
            <span className="font-medium text-purple-300">Ready for craft review</span>
          </div>
        </div>
      ) : (
        <div className="relative z-10 flex flex-col items-center text-center">
          <div className="dropzone-icon-shell">
            <UploadCloud className="h-8 w-8" strokeWidth={1.6} />
          </div>
          <p className="mt-5 text-base font-bold text-white sm:text-lg">
            <span className="sm:hidden">Tap to choose your video</span>
            <span className="hidden sm:inline">Drop your video here</span>
          </p>
          <p className="mt-1.5 text-sm text-zinc-400">
            <span className="hidden sm:inline">or click to browse · </span>MP4 or MOV · up to 10 min
          </p>
          <div className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-black/20 px-3 py-1.5 text-[11px] text-zinc-500">
            <Sparkles className="h-3.5 w-3.5 text-purple-400" />
            {idleNote}
          </div>
        </div>
      )}
    </div>
  );
}
