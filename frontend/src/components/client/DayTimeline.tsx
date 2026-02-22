"use client";

import { useState } from "react";
import { Clock, MapPin, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import DisruptionModal from "./DisruptionModal";

interface Activity {
    id: number;
    time: string;
    title: string;
    location: string;
    status: "normal" | "issue";
}

const initialActivities: Activity[] = [
    { id: 1, time: "09:00 AM", title: "Breakfast at Tiffany's", location: "5th Avenue", status: "normal" },
    { id: 2, time: "11:00 AM", title: "Museum Tour", location: "The Met", status: "normal" },
    { id: 3, time: "01:00 PM", title: "Lunch with Client", location: "Central Park Boathouse", status: "normal" },
];

export default function DayTimeline() {
    const [activities, setActivities] = useState(initialActivities);
    const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null);

    const handleReport = () => {
        if (selectedActivityId) {
            setActivities(activities.map(a =>
                a.id === selectedActivityId ? { ...a, status: "issue" } : a
            ));
            setSelectedActivityId(null);
        }
    };

    return (
        <div className="p-6 max-w-md mx-auto space-y-8 pb-32">
            {/* Map Placeholder */}
            <div className="h-40 rounded-xl bg-navy-800 border border-white/10 flex items-center justify-center relative overflow-hidden group">
                <div className="absolute inset-0 bg-[url('https://api.mapbox.com/styles/v1/mapbox/dark-v10/static/-74.006,40.7128,12,0/600x400?access_token=pk.xxx')] bg-cover bg-center opacity-50 grayscale group-hover:grayscale-0 transition-all duration-500" />
                <div className="relative z-10 flex items-center gap-2 text-cyan-400 font-medium">
                    <MapPin className="w-5 h-5" />
                    Interactive Map
                </div>
            </div>

            {/* Timeline */}
            <div className="space-y-6 relative border-l border-white/10 ml-4 pl-8">
                {activities.map((activity) => (
                    <div key={activity.id} className="relative">
                        {/* Timeline Dot */}
                        <div className={`absolute -left-[39px] top-1 w-5 h-5 rounded-full border-4 border-navy-950 ${activity.status === 'issue' ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]' : 'bg-cyan-500'}`} />

                        <div className={`glass-card p-4 rounded-xl border transition-colors ${activity.status === 'issue' ? 'border-red-500/30 bg-red-500/5' : 'border-white/5'}`}>
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2 text-gray-400 text-sm">
                                    <Clock className="w-3 h-3" />
                                    {activity.time}
                                </div>
                                {activity.status === 'issue' && (
                                    <span className="flex items-center gap-1 text-xs text-red-400 font-bold uppercase tracking-wider">
                                        <AlertCircle className="w-3 h-3" /> Issue
                                    </span>
                                )}
                            </div>

                            <h3 className="font-bold text-lg mb-1">{activity.title}</h3>
                            <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
                                <MapPin className="w-3 h-3" />
                                {activity.location}
                            </div>

                            <Button
                                variant="outline"
                                size="sm"
                                className={`w-full border-dashed ${activity.status === 'issue' ? 'text-red-400 border-red-500/30 hover:bg-red-500/10' : 'text-gray-400 border-white/20 hover:text-white hover:border-white/40'}`}
                                onClick={() => setSelectedActivityId(activity.id)}
                            >
                                {activity.status === 'issue' ? 'Update Issue' : 'Report Disruption'}
                            </Button>
                        </div>
                    </div>
                ))}
            </div>

            <DisruptionModal
                isOpen={!!selectedActivityId}
                onClose={() => setSelectedActivityId(null)}
                onSubmit={handleReport}
                activityTitle={activities.find(a => a.id === selectedActivityId)?.title || ""}
            />
        </div>
    );
}
