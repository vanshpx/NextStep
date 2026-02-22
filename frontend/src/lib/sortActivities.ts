/**
 * Backend-only utility for computing persistent activity order values.
 * Called on every write (create / update / delete) — never on GET or frontend.
 */

/**
 * Normalises a raw time string to strict 24-hour HH:MM format.
 * Accepts both "HH:MM" (24h) and "H:MM" variants.
 * Returns "" for blank or unparseable input so those activities sort last.
 */
export function normalizeTime(raw: string): string {
    if (!raw || typeof raw !== 'string') return '';
    const trimmed = raw.trim();

    // Already HH:MM 24h (e.g. "09:30", "14:00")
    const match24 = trimmed.match(/^(\d{1,2}):(\d{2})$/);
    if (match24) {
        const h = parseInt(match24[1], 10);
        const m = parseInt(match24[2], 10);
        if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
            return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
        }
    }
    return ''; // Unrecognised — treat as un-timed (sorts to end)
}

/**
 * Given an array of activities, returns the same activities augmented with
 * a 1-based `order` value derived from chronological sort of their times.
 * Activities with empty/invalid time are placed at the end.
 * Relative order of same-time activities is preserved (stable sort via index).
 */
export function computeActivityOrder<T extends { time: string }>(
    activities: T[]
): (T & { order: number })[] {
    const withNormalized = activities.map((act, originalIndex) => ({
        act,
        normalized: normalizeTime(act.time),
        originalIndex,
    }));

    // Stable sort: primary key = normalized time (empty last), secondary = original index
    withNormalized.sort((a, b) => {
        if (!a.normalized && !b.normalized) return a.originalIndex - b.originalIndex;
        if (!a.normalized) return 1;
        if (!b.normalized) return -1;
        const cmp = a.normalized.localeCompare(b.normalized);
        return cmp !== 0 ? cmp : a.originalIndex - b.originalIndex;
    });

    return withNormalized.map(({ act }, i) => ({ ...act, order: i + 1 }));
}
