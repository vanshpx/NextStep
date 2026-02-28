export interface BaseActivity {
    id: string | number;
    title: string;
    startTime: string; // UTC ISO string (e.g., "2026-02-24T10:00:00.000Z")
    isDisrupted?: boolean;
}

export interface SequentialActivity extends BaseActivity {
    endTime: string; // Guaranteed UTC ISO string
}

export function enforceSequentialTimeline<T extends BaseActivity>(activities: T[]): (T & SequentialActivity)[] {
    if (!activities || activities.length === 0) return [];

    // 1. Sort safely by deterministic UTC time
    const sorted = [...activities].sort((a, b) =>
        new Date(a.startTime).getTime() - new Date(b.startTime).getTime()
    );

    return sorted.map((activity, index) => {
        let endTimeIso: string;

        // If there is a next activity, our end time = their start time
        if (index < sorted.length - 1) {
            endTimeIso = sorted[index + 1].startTime;
        } else {
            // Last activity: default to 2 hours duration
            const start = new Date(activity.startTime);
            const endMs = start.getTime() + (2 * 60 * 60 * 1000); // Add 2 hours
            endTimeIso = new Date(endMs).toISOString();
        }

        return {
            ...activity,
            endTime: endTimeIso,
        };
    });
}
