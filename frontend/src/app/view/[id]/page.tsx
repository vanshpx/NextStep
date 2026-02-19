"use client";

import { useState, use } from 'react';
import { motion } from 'framer-motion';
import { MapPin, Calendar, Info, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import DisruptionModal from '@/components/client/DisruptionModal';
import { useItinerary, Activity } from '@/context/ItineraryContext'; // Import from Context
import Link from 'next/link';

// Dynamically import the map to avoid SSR issues
import dynamic from 'next/dynamic';

const ClientMap = dynamic(() => import('@/components/client/ClientMap'), {
    ssr: false,
    loading: () => (
        <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400">
            Loading Map...
        </div>
    ),
});

export default function ClientViewPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    return <ClientViewContent id={id} />;
}

function ClientViewContent({ id }: { id: string }) {
    const { getItinerary, updateItinerary, isLoading } = useItinerary();
    const itinerary = getItinerary(parseInt(id)); // Fetch from context

    const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null);
    const [disruptionActivity, setDisruptionActivity] = useState<Activity | null>(null);

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-xl text-gray-500 font-medium">Loading your trip...</div>
            </div>
        );
    }

    // Handle 404
    if (!itinerary) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50 flex-col">
                <h1 className="text-2xl font-bold text-gray-900 mb-2">Itinerary Not Found</h1>
                <p className="text-gray-500 mb-4">The trip you are looking for does not exist.</p>
                <Link href="/dashboard">
                    <Button variant="outline">Back to Dashboard</Button>
                </Link>
            </div>
        );
    }

    const handleDisruptionSubmit = async (type: string, details?: string) => {
        console.log("Disruption reported:", type, details, "for activity:", disruptionActivity?.title);

        try {
            await updateItinerary(itinerary.id, {
                status: 'Disrupted'
                // In a real app, we would append to an issues log or audit trail here
            });
            alert(`Issue reported for ${disruptionActivity?.title}. Support team has been notified.`);
        } catch (error) {
            console.error("Failed to report disruption", error);
            alert("Failed to report issue. Please try again.");
        }

        setDisruptionActivity(null);
    };

    // Fallback data if itineraryDays is missing (for older mocks)
    const days = itinerary.itineraryDays || [];
    const totalDays = itinerary.totalDays || days.length;
    const origin = itinerary.from || itinerary.origin || "Origin";
    const destination = itinerary.to || itinerary.d || "Destination";

    // Mock Progress Calculation
    // If completed, show 100%. Else use demo logic (Day 2)
    const isTripCompleted = itinerary.status === 'Completed';
    const currentDay = isTripCompleted ? totalDays : 2;
    const progress = isTripCompleted ? 100 : (currentDay / totalDays) * 100;

    return (
        <div className="min-h-screen bg-gray-50 font-sans">
            {/* Split Layout Container */}
            <div className="flex flex-col lg:flex-row h-screen overflow-hidden">

                {/* Left Panel - Scrollable Itinerary (50% on Desktop) */}
                <div className="w-full lg:w-1/2 h-full flex flex-col border-r border-gray-200 bg-white overflow-y-auto">
                    {/* Header */}
                    <header className="sticky top-0 z-20 bg-white/90 backdrop-blur-md border-b border-gray-100 px-6 py-4">
                        <div className="flex justify-between items-center mb-4">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">{itinerary.c}</h1>
                                <div className="flex items-center gap-2 text-gray-500 text-sm mt-1">
                                    <span>{origin}</span>
                                    <MapPin className="w-4 h-4 text-primary-500" />
                                    <span>{destination}</span>
                                    <span className="mx-2">•</span>
                                    <Calendar className="w-4 h-4 text-primary-500" />
                                    <span>{totalDays} Days</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-sm font-medium text-primary-700 mb-1">Trip Progress</div>
                                <div className="w-32 h-2 bg-gray-100 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary-500 transition-all duration-1000 ease-out"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        </div>
                    </header>

                    {/* Timeline Content */}
                    <div className="p-6 space-y-8">
                        {days.map((day, index) => {
                            // Determine status
                            let status = 'upcoming';
                            if (isTripCompleted) {
                                status = 'completed';
                            } else {
                                // Demo Logic: Day 1 = Completed, Day 2 = Active, Day 3 = Upcoming
                                status = index === 0 ? 'completed' : index === 1 ? 'active' : 'upcoming';
                            }

                            const isCompleted = status === 'completed';
                            const isActive = status === 'active';

                            return (
                                <motion.div
                                    key={day.id}
                                    initial={{ opacity: 0, y: 20 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ duration: 0.3, ease: 'easeOut' }}
                                    className="relative pb-12 last:pb-0"
                                >
                                    <h3
                                        className={`text-lg font-bold mb-4 flex items-center gap-2 ${isCompleted ? 'text-green-700' : isActive ? 'text-primary-700' : 'text-gray-900'
                                            }`}
                                    >
                                        Day {day.dayNumber}
                                        {isActive && <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full font-medium">Today</span>}
                                        {isCompleted && <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">Completed</span>}
                                    </h3>

                                    <div className="space-y-0 relative">
                                        {/* Activity Connector Line for the Day */}
                                        <div className="absolute left-4 top-4 bottom-4 w-0.5 bg-gray-100 z-0" />

                                        {day.activities.map((activity, actIndex) => {
                                            // Determine activity status
                                            let actStatus = 'upcoming';

                                            if (isTripCompleted) {
                                                actStatus = 'completed';
                                            } else {
                                                // Mock Logic
                                                if (index < 1) { // Day 1
                                                    actStatus = 'completed';
                                                } else if (index === 1) { // Day 2
                                                    if (actIndex === 0) actStatus = 'completed';
                                                    else if (actIndex === 1) actStatus = 'current';
                                                    else actStatus = 'upcoming';
                                                }
                                            }

                                            const isActCompleted = actStatus === 'completed';
                                            const isActCurrent = actStatus === 'current';

                                            return (
                                                <div
                                                    key={activity.id}
                                                    className="relative pl-12 py-2"
                                                >
                                                    {/* Activity Dot on local timeline */}
                                                    <div
                                                        className={`absolute left-[13px] top-6 w-2.5 h-2.5 rounded-full z-10 border-2 ${isActCompleted
                                                            ? 'bg-green-500 border-green-500'
                                                            : isActCurrent
                                                                ? 'bg-primary-600 border-primary-600 shadow-[0_0_10px_rgba(37,99,235,0.6)] animate-pulse'
                                                                : 'bg-white border-gray-300'
                                                            }`}
                                                    />

                                                    {/* Connector Line Coloring */}
                                                    {/* This covers the gray line with green if completed */}
                                                    <div
                                                        className={`absolute left-4 top-0 h-full w-0.5 z-0 ${isActCompleted ? 'bg-green-500' : 'bg-transparent'
                                                            }`}
                                                        style={{
                                                            height: isActCurrent ? '50%' : isActCompleted ? '100%' : '0%',
                                                            transition: 'height 0.5s ease-out'
                                                        }}
                                                    />

                                                    {/* Activity Card */}
                                                    <div
                                                        className={`group relative bg-white p-4 rounded-xl border transition-all duration-300 ${isActCompleted
                                                            ? 'border-gray-200 bg-gray-50/50 opacity-100' // Changed from green
                                                            : isActCurrent
                                                                ? 'border-primary-500 shadow-md ring-1 ring-primary-100'
                                                                : 'border-gray-100 hover:border-gray-200 hover:shadow-lg'
                                                            }`}
                                                    >
                                                        <div className="flex gap-4">
                                                            <div className="flex-shrink-0 w-16 text-center">
                                                                <div className={`text-sm font-bold ${isActCurrent ? 'text-primary-700' : 'text-gray-900'}`}>{activity.time}</div>
                                                                <div className="text-xs text-gray-400 uppercase tracking-wider">{parseInt(activity.time) < 12 ? 'AM' : 'PM'}</div>
                                                            </div>

                                                            <div className="flex-1">
                                                                <h4 className={`font-bold transition-colors mb-1 ${isActCompleted ? 'text-gray-500' : 'text-gray-900 group-hover:text-primary-700'}`}>
                                                                    {activity.title}
                                                                </h4>
                                                                <div className="flex items-center text-sm text-gray-500 mb-2">
                                                                    <MapPin className="w-3 h-3 mr-1 text-gray-400" />
                                                                    {activity.location}
                                                                </div>
                                                                {activity.notes && (
                                                                    <div className="text-sm text-gray-600 bg-white p-2 rounded border border-gray-100">
                                                                        {activity.notes}
                                                                    </div>
                                                                )}
                                                            </div>

                                                            {/* View on Map Button */}
                                                            {/* View on Map Button */}
                                                            <div className="flex flex-col gap-2 justify-between">
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    onClick={(e: React.MouseEvent) => {
                                                                        e.stopPropagation();
                                                                        setSelectedActivity(activity);
                                                                    }}
                                                                    className="text-primary-600 hover:text-primary-700 hover:bg-primary-50"
                                                                    title="View on Map"
                                                                >
                                                                    <MapPin className="w-4 h-4" />
                                                                </Button>

                                                                {isActCurrent && (
                                                                    <Button
                                                                        variant="ghost"
                                                                        size="sm"
                                                                        onClick={(e: React.MouseEvent) => {
                                                                            e.stopPropagation();
                                                                            setDisruptionActivity(activity);
                                                                        }}
                                                                        className="text-red-400 hover:text-red-600 hover:bg-red-50 mt-auto"
                                                                        title="Report Issue"
                                                                    >
                                                                        <AlertTriangle className="w-4 h-4" />
                                                                    </Button>
                                                                )}
                                                            </div>
                                                        </div>

                                                        {/* Status Tags */}
                                                        {isActCurrent && (
                                                            <div className="absolute -top-2.5 left-4 px-2 py-0.5 bg-primary-600 text-white text-[10px] font-bold uppercase tracking-wider rounded-full shadow-sm">
                                                                Now Happening
                                                            </div>
                                                        )}

                                                        {activity.status === 'issue' && (
                                                            <div className="absolute top-2 right-2 px-2 py-0.5 bg-red-100 text-red-600 text-xs font-bold rounded-full border border-red-200 animate-pulse">
                                                                Issue Reported
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>

                {/* Right Panel - Map & Info (50% on Desktop, Hidden on Mobile initially) */}
                <div className="hidden lg:flex w-1/2 h-full flex-col bg-gray-100 border-l border-gray-200">
                    {/* Map Section (Top 60%) */}
                    <div className="h-[60%] relative bg-gray-200 overflow-hidden group">
                        <ClientMap
                            activities={days.flatMap(d => d.activities)}
                            selectedActivity={selectedActivity}
                        />
                    </div>

                    {/* Bottom Recommendations/Details Section (Bottom 40%) */}
                    <div className="h-[40%] bg-white border-t border-gray-200 p-6 overflow-y-auto">
                        <div className="flex items-center gap-2 mb-4">
                            <Info className="w-5 h-5 text-primary-600" />
                            <h3 className="text-lg font-bold text-gray-900">Local Recommendations</h3>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            {[1, 2, 3, 4].map((i) => (
                                <div key={i} className="p-4 rounded-lg border border-gray-100 hover:border-primary-200 hover:shadow-md transition-all cursor-pointer bg-gray-50 flex gap-3">
                                    <div className="w-12 h-12 rounded bg-gray-200 flex-shrink-0" />
                                    <div>
                                        <div className="h-4 w-24 bg-gray-200 rounded mb-2" />
                                        <div className="h-3 w-16 bg-gray-100 rounded" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Disruption Modal */}
                {/* Disruption Modal */}
                {disruptionActivity && (
                    <DisruptionModal
                        isOpen={!!disruptionActivity}
                        onClose={() => setDisruptionActivity(null)}
                        onSubmit={handleDisruptionSubmit}
                        activityTitle={disruptionActivity?.title || ''}
                    />
                )}
            </div>
        </div>
    );
}
