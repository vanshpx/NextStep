import { useMemo } from 'react';
import { useGlobalTime } from './useGlobalTime';

export type ActivityStatus =
    | 'Upcoming'
    | 'Now Happening'
    | 'Completed'
    | 'Disrupted'
    | 'Missed / Disrupted';

export function useActivityStatus(
    startTimeIso: string,
    endTimeIso: string,
    isDisrupted: boolean = false
) {
    const currentTimestamp = useGlobalTime();

    return useMemo(() => {
        const startMs = new Date(startTimeIso).getTime();
        const endMs = new Date(endTimeIso).getTime();

        // 1. Calculate Progress: Clamp safely between 0 and 100
        let progressPercentage = 0;
        if (currentTimestamp >= endMs) {
            progressPercentage = 100;
        } else if (currentTimestamp > startMs) {
            const elapsed = currentTimestamp - startMs;
            const duration = endMs - startMs;
            progressPercentage = Math.min(100, Math.max(0, (elapsed / duration) * 100));
        }

        // 2. Determine Status Output
        let status: ActivityStatus = 'Upcoming';

        if (isDisrupted) {
            // Disruption overrides chronical status but relies on time bounds
            if (currentTimestamp >= endMs) {
                status = 'Missed / Disrupted';
            } else {
                status = 'Disrupted';
            }
        } else {
            // Standard flow
            if (currentTimestamp < startMs) {
                status = 'Upcoming';
            } else if (currentTimestamp >= endMs) {
                status = 'Completed';
            } else {
                status = 'Now Happening';
            }
        }

        return { status, progressPercentage };
    }, [currentTimestamp, startTimeIso, endTimeIso, isDisrupted]);
}
