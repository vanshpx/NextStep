"use client";

import { Itinerary } from "@prisma/client";

interface TripHeaderProps {
    clientName: string;
    from: string;
    to: string;
    totalDays: number;
    currentDay: number;
    status: Itinerary['status'];
}

export default function TripHeader({ clientName, from, to, totalDays, currentDay, status }: TripHeaderProps) {
    const progress = (status === 'Draft' || status === 'Upcoming') ? 0 : (currentDay / totalDays) * 100;

    return (
        <div className="bg-navy-900 border-b border-white/5 pb-6 pt-12 px-6 sticky top-0 z-30 shadow-xl">
            <div className="max-w-md mx-auto">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h1 className="text-2xl font-bold text-white mb-1">Trip to {to}</h1>
                        <p className="text-gray-400 text-sm">{clientName} • {from} → {to}</p>
                    </div>
                    <div className="text-right">
                        <span className="text-cyan-400 font-bold text-xl">{totalDays}</span>
                        <span className="text-gray-500 text-sm block">Days</span>
                    </div>
                </div>

                <div className="space-y-2">
                    <div className="flex justify-between text-xs text-gray-400 uppercase tracking-wider">
                        <span>Trip Progress</span>
                        <span>Day {currentDay} of {totalDays}</span>
                    </div>
                    <div className="h-2 bg-navy-950 rounded-full overflow-hidden border border-white/5">
                        <div
                            className="h-full bg-cyan-500 shadow-[0_0_10px_rgba(0,229,255,0.5)] transition-all duration-1000"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
