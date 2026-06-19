const ALLOWED_VIDEO_TYPES = new Set(["video/mp4", "video/quicktime"]);
const ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".mov"];

export function isAllowedVideoFile(file: File) {
  const type = file.type.toLowerCase();
  if (type) return ALLOWED_VIDEO_TYPES.has(type);

  const name = file.name.toLowerCase();
  return ALLOWED_VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function uploadContentTypeFor(file: File) {
  const type = file.type.toLowerCase();
  if (ALLOWED_VIDEO_TYPES.has(type)) return type;
  return file.name.toLowerCase().endsWith(".mov") ? "video/quicktime" : "video/mp4";
}
