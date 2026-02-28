import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Shortens a comma-separated location string.
 * Keeps the first segment (POI/Street), second-to-last (City), and last (Country).
 * Example: "POI, Area, City, State, Country" -> "POI, City, Country"
 */
export function formatLocation(location: string | null | undefined): string {
  if (!location) return "";
  const segments = location.split(",").map(s => s.trim());

  if (segments.length < 3) return location;

  // Keep first segment
  const first = segments[0];
  // Keep last segment
  const last = segments[segments.length - 1];
  // Keep the city segment (conventionally 3rd from last in Google standard addresses)
  const city = segments[segments.length - 3];

  // Return deduped segments to handle shorter addresses naturally
  const result = Array.from(new Set([first, city, last]));
  return result.join(", ");
}
