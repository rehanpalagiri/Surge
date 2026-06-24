// Mirror backend ALLOWED_CONTENT_TYPES (routers/analyze.py). These are the
// formats Gemini's File API accepts natively. MKV is intentionally excluded
// (Gemini does not support it). Browsers report several MIME spellings per
// format, so include the common variants (e.g. AVI is usually x-msvideo).
const ALLOWED_VIDEO_TYPES = new Set([
  "video/mp4",
  "video/quicktime",                  // .mov
  "video/webm",
  "video/avi", "video/x-msvideo",     // .avi
  "video/mpeg", "video/mpg", "video/x-mpeg",  // .mpeg / .mpg
  "video/wmv", "video/x-ms-wmv",      // .wmv
  "video/x-flv",                      // .flv
  "video/3gpp",                       // .3gp
]);

const ALLOWED_VIDEO_EXTENSIONS = [
  ".mp4", ".mov", ".webm", ".avi", ".mpeg", ".mpg", ".wmv", ".flv", ".3gp",
];

// Maps an extension to the MIME type the backend expects when the browser
// reports no (or an unrecognized) type. Keep keys in sync with the backend.
const EXTENSION_CONTENT_TYPES: Array<[string, string]> = [
  [".mov", "video/quicktime"],
  [".webm", "video/webm"],
  [".avi", "video/x-msvideo"],
  [".mpeg", "video/mpeg"],
  [".mpg", "video/mpeg"],
  [".wmv", "video/x-ms-wmv"],
  [".flv", "video/x-flv"],
  [".3gp", "video/3gpp"],
  [".mp4", "video/mp4"],
];

export function isAllowedVideoFile(file: File) {
  const type = file.type.toLowerCase();
  if (type) return ALLOWED_VIDEO_TYPES.has(type);

  const name = file.name.toLowerCase();
  return ALLOWED_VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function uploadContentTypeFor(file: File) {
  const type = file.type.toLowerCase();
  if (ALLOWED_VIDEO_TYPES.has(type)) return type;

  const name = file.name.toLowerCase();
  const match = EXTENSION_CONTENT_TYPES.find(([ext]) => name.endsWith(ext));
  return match ? match[1] : "video/mp4";
}
