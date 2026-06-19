import { API_BASE } from "./api";
import type { Person } from "./types";

export const REAL_SCREENSHOT_PREFIX = "anonymized_screenshots/";
export const UPLOADED_SCREENSHOT_PREFIX = "uploads/";

export function isUpdatedContactPerson(person: Pick<Person, "raw_screenshot_ref">): boolean {
  return (
    person.raw_screenshot_ref.startsWith(REAL_SCREENSHOT_PREFIX) ||
    person.raw_screenshot_ref.startsWith(UPLOADED_SCREENSHOT_PREFIX)
  );
}

export function screenshotFileName(person: Pick<Person, "raw_screenshot_ref">): string {
  if (person.raw_screenshot_ref.startsWith(REAL_SCREENSHOT_PREFIX)) {
    return person.raw_screenshot_ref.slice(REAL_SCREENSHOT_PREFIX.length);
  }
  if (person.raw_screenshot_ref.startsWith(UPLOADED_SCREENSHOT_PREFIX)) {
    return person.raw_screenshot_ref.slice(UPLOADED_SCREENSHOT_PREFIX.length);
  }
  return person.raw_screenshot_ref;
}

export function screenshotUrlForPerson(
  person: Pick<Person, "raw_screenshot_ref">,
  previews: Record<string, string> = {},
): string | null {
  const preview = previews[person.raw_screenshot_ref];
  if (preview) return preview;
  if (!person.raw_screenshot_ref.startsWith(REAL_SCREENSHOT_PREFIX)) return null;
  const fileName = screenshotFileName(person);
  if (!fileName || fileName.includes("/") || fileName.includes("\\")) return null;
  return `${API_BASE}/assets/screenshots/${encodeURIComponent(fileName)}`;
}
