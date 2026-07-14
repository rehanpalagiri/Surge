"use client";

import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import { CheckCircle2, FileVideo2, UploadCloud } from "lucide-react";

interface ReactiveVideoDropzoneProps {
  file: File | null;
  onFileSelected: (file: File) => void | Promise<void>;
  selectedDetail?: ReactNode;
  disabled?: boolean;
}

type DropzoneStyle = CSSProperties & {
  "--drop-x"?: string;
  "--drop-y"?: string;
};

function getDroppedFile(dataTransfer: DataTransfer): File | undefined {
  // macOS apps such as Messages can expose an attachment through drag items
  // before (or instead of) populating the FileList used by a standard browser
  // file picker. Prefer the item payload, then retain the FileList fallback.
  for (const item of Array.from(dataTransfer.items)) {
    if (item.kind === "file") {
      const file = item.getAsFile();
      if (file) return file;
    }
  }

  return Array.from(dataTransfer.files).find((file) => file instanceof File);
}

function hasDroppedFile(dataTransfer: DataTransfer) {
  return Array.from(dataTransfer.items).some((item) => item.kind === "file") ||
    dataTransfer.types.includes("Files");
}

export default function ReactiveVideoDropzone({
  file,
  onFileSelected,
  selectedDetail,
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
    if (disabled || !hasDroppedFile(event.dataTransfer)) return;
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
    event.stopPropagation();
    dragDepth.current = 0;
    setDragging(false);
    receiveFile(getDroppedFile(event.dataTransfer));
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (disabled || !hasDroppedFile(event.dataTransfer)) return;
    event.dataTransfer.dropEffect = "copy";
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
      onDragOver={handleDragOver}
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
            <p className="text-lg font-bold text-text-primary">Release to add your video</p>
            <p className="mt-1 text-sm text-text-muted">We&apos;ll validate it immediately</p>
          </div>
        </div>
      ) : file ? (
        <div className="relative z-10 w-full max-w-lg motion-pop">
          <div className="mb-4 flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
              <CheckCircle2 className="h-3.5 w-3.5" /> Ready
            </span>
            <span className="text-xs text-text-muted">Tap anywhere to replace</span>
          </div>

          <div className="flex items-center gap-4 text-left">
            <div className="dropzone-file-icon">
              <FileVideo2 className="h-7 w-7" strokeWidth={1.6} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-semibold text-text-primary">{file.name}</p>
              <div className="mt-1 text-xs text-text-muted">{selectedDetail}</div>
            </div>
          </div>

          <div className="dropzone-ready-track mt-5" aria-hidden="true">
            <div className="dropzone-ready-fill" />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px]">
            <span className="text-text-muted">File checked</span>
            <span className="font-medium text-success">Ready for craft review</span>
          </div>
        </div>
      ) : (
        <div className="relative z-10 flex flex-col items-center text-center">
          <div className="dropzone-icon-shell">
            <UploadCloud className="h-8 w-8" strokeWidth={1.6} />
          </div>
          <p className="mt-5 text-base font-bold text-text-primary sm:text-lg">
            <span className="sm:hidden">Tap to choose your video</span>
            <span className="hidden sm:inline">Drop your video here</span>
          </p>
          <p className="mt-1.5 text-sm text-text-muted">
            <span className="hidden sm:inline">or click to browse</span>
            <span className="sm:hidden">Choose a video from your device</span>
          </p>
        </div>
      )}
    </div>
  );
}
