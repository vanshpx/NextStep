"use client";

import { useState, use, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
    CheckCircle2, Clock, PlayCircle, AlertCircle,
    PlaneTakeoff, Hotel, Phone, Handshake, Info, Asterisk,
    MapPin, Calendar, AlertTriangle, PlaneLanding, BedDouble
} from "lucide-react";
import { Button } from '@/components/ui/Button';
import DisruptionModal from '@/components/client/DisruptionModal';
import { useItinerary, Activity } from '@/context/ItineraryContext'; // Import from Context
import { formatLocation } from '@/lib/utils';
import Link from 'next/link';
import { enforceSequentialTimeline, BaseActivity, SequentialActivity } from '@/utils/activityLogic';
import { useActivityStatus } from '@/hooks/useActivityStatus';
import { useGlobalTime } from '@/hooks/useGlobalTime';
import { toast } from 'sonner';

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

/*
 * Decoupled Time-driven Components
 */

function TripProgressBar({ timeline, isDraft }: { timeline: SequentialActivity[], isDraft: boolean }) {
    const now = useGlobalTime();
    let progress = 0;
    if (isDraft || timeline.length === 0) {
        progress = 0;
    } else {
        const firstStart = new Date(timeline[0].startTime).getTime();
        const lastEnd = new Date(timeline[timeline.length - 1].endTime).getTime();
        if (now >= lastEnd) progress = 100;
        else if (now <= firstStart) progress = 0;
        else progress = Math.min(100, Math.max(0, ((now - firstStart) / (lastEnd - firstStart)) * 100));
    }

    return (
        <div className="w-32 h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-primary-500 transition-all duration-1000 ease-out" style={{ width: `${progress}%` }} />
        </div>
    );
}

function DayTimelineBlock({
    day,
    activities,
    isTripCompleted,
    isDisruptedGlobal,
    onViewMap,
    onReportIssue,
    itineraryIssueSummary
}: {
    day: any,
    activities: (SequentialActivity & Activity)[],
    isTripCompleted: boolean,
    isDisruptedGlobal?: boolean,
    onViewMap: (a: any) => void,
    onReportIssue: (a: any) => void,
    itineraryIssueSummary?: string
}) {
    const now = useGlobalTime();

    const allCompleted = activities.every(a => now >= new Date(a.endTime).getTime());
    const isActActive = activities.some(a => {
        const start = new Date(a.startTime).getTime();
        const end = new Date(a.endTime).getTime();
        return now >= start && now < end;
    });

    const isCompleted = isTripCompleted || allCompleted;
    const isActive = !isCompleted && isActActive;

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.3, ease: 'easeOut' }} className="relative pb-12 last:pb-0">
            <h3 className="text-xl font-black text-gray-950 mb-4 flex items-center gap-3">
                Day {day.dayNumber}
                {isActive && <span className="text-[11px] bg-primary-50 text-primary-700 px-3 py-1 rounded-full font-bold uppercase tracking-wider">Today</span>}
                {isCompleted && <span className="booking-badge-success">Completed</span>}
            </h3>
            <div className="space-y-0 relative">
                <div className="absolute left-4 top-4 bottom-4 w-[1.5px] bg-gray-100 z-0" />
                {activities.map((activity) => (
                    <TimelineActivityCard
                        key={activity.id}
                        activity={activity}
                        onViewMap={() => onViewMap(activity)}
                        onReportIssue={() => onReportIssue(activity)}
                        itineraryIssueSummary={activity.status === 'issue' ? (itineraryIssueSummary || 'Disrupted') : undefined}
                    />
                ))}
            </div>
        </motion.div>
    );
}

function TimelineActivityCard({
    activity,
    onViewMap,
    onReportIssue,
    itineraryIssueSummary
}: {
    activity: SequentialActivity & Activity;
    onViewMap: () => void;
    onReportIssue: () => void;
    itineraryIssueSummary?: string;
}) {
    // Only disrupted if its own status is issue or if its explicitly marked
    const isDisrupted = activity.status === 'issue';
    const { status, progressPercentage } = useActivityStatus(activity.startTime, activity.endTime, isDisrupted);

    const isActCompleted = status === 'Completed' || status === 'Missed / Disrupted';
    const isActCurrent = status === 'Now Happening' || status === 'Disrupted';
    const isRedVariant = status.includes('Disrupted');

    // Get the disruption message - use activity notes if available, otherwise use itinerary summary
    const disruptionMessage = isDisrupted && activity.notes ? activity.notes : itineraryIssueSummary;

    return (
        <div className="relative pl-12 pb-8 last:pb-0 group">
            {/* Activity Dot */}
            <div className={`absolute left-[10.75px] top-6 w-3 h-3 rounded-full z-10 border-2 transition-transform scale-110 ${
                isActCompleted ? 
                    (status === 'Missed / Disrupted' ? 'bg-red-600 border-red-600' : 'bg-[var(--success)] border-[var(--success)]') 
                : isActCurrent ? 
                    isRedVariant ? 'bg-red-600 border-red-600 shadow-[0_0_10px_rgba(220,38,38,0.6)] animate-pulse' 
                    : 'bg-primary-600 border-primary-600 shadow-[0_0_10px_rgba(37,99,235,0.6)] animate-pulse' 
                : 'bg-white border-gray-300'
            }`} />
            {/* Timeline Line */}
            <div className="absolute left-4 top-0 h-full w-[1.5px] bg-gray-200 z-0" />
            {/* Timeline Progress Line */}
            <div className={`absolute left-4 top-0 w-[1.5px] z-1 ${isActCompleted ? 'bg-[var(--success)]' : 'bg-transparent'}`} style={{ height: isActCurrent ? '50%' : isActCompleted ? '100%' : '0%', transition: 'height 0.5s ease-out' }} />

            <div className={`booking-card relative p-5 transition-all duration-300 shadow hover:shadow-md ${isActCurrent ? isRedVariant ? 'shadow-red-500/40 border-red-200/50' : 'shadow-primary-500/30 border-primary-200/50' : ''}`}>
                <div className="absolute top-4 right-4">
                    <Button variant="ghost" size="sm" onClick={onViewMap} className="text-green-800 hover:text-green-900 hover:bg-green-50 p-2 h-auto" title="View on Map"><MapPin className="w-4 h-4" /></Button>
                </div>
                <div className="flex gap-5">
                    <div className="flex-shrink-0 w-16 text-center pt-0.5">
                        <div className={`text-[15px] font-black tracking-tight ${isActCurrent ? isRedVariant ? 'text-red-700' : 'text-primary-700' : 'text-gray-900'}`}>{activity.time}</div>
                        <div className="text-[10px] text-gray-400 font-bold uppercase tracking-[0.1em]">{parseInt(activity.time) < 12 ? 'AM' : 'PM'}</div>
                    </div>
                    <div className="flex-1">
                        <h4 className="text-[17px] font-black text-gray-950 leading-tight tracking-[-0.015em] transition-colors mb-1 group-hover:text-primary-700">{activity.title}</h4>
                        <div className="text-[14px] text-gray-500 mb-3 font-medium flex items-center gap-1.5">
                            <MapPin className="w-3.5 h-3.5 text-gray-400" />{formatLocation(activity.location)}
                        </div>
                        {activity.notes && !isDisrupted && <div className="text-[13px] text-gray-400 italic font-medium mt-2">&quot;{activity.notes}&quot;</div>}
                    </div>
                </div>

                {/* Bottom-Right Action: Report Issue (Current Only) */}
                {isActCurrent && !isDisrupted && (
                    <div className="absolute bottom-4 right-4">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={onReportIssue}
                            className="text-red-400 hover:text-red-600 hover:bg-red-50 p-2 h-auto"
                            title="Report Issue"
                        >
                            <AlertTriangle className="w-4 h-4" />
                        </Button>
                    </div>
                )}
            </div>

            {/* Status Tags */}
            {isActCurrent && (
                <div className={`absolute -top-2.5 left-20 px-2 py-0.5 text-white text-[10px] font-bold uppercase tracking-wider rounded-full shadow-sm ${isRedVariant ? 'bg-red-600' : 'bg-primary-600'}`}>
                    {isRedVariant ? (disruptionMessage || 'Activity Disrupted') : 'Now Happening'}
                </div>
            )}
        </div>
    );
}

export default function ClientViewPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    return <ClientViewContent id={id} />;
}

function ClientViewContent({ id }: { id: string }) {
    const { getItinerary, updateItinerary, updateActivity, isLoading } = useItinerary();
    const itinerary = getItinerary(parseInt(id)); // Fetch from context

    const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null);
    const [disruptionActivity, setDisruptionActivity] = useState<Activity | null>(null);

    const days = itinerary?.itineraryDays || [];

    const timelineActivities = useMemo(() => {
        if (!itinerary) return [];
        const startDateRaw = itinerary.flights?.find((f: any) => f.type === 'Departure')?.date || new Date().toISOString();
        const startDate = new Date(startDateRaw);

        const baseActivities: (BaseActivity & Activity)[] = days.flatMap((d: any) => {
            return d.activities.map((a: Activity) => {
                const actDate = new Date(startDate);
                // Use local date methods instead of UTC to match useGlobalTime
                actDate.setDate(actDate.getDate() + (d.dayNumber - 1));
                if (a.time) {
                    const parts = a.time.split(':');
                    if (parts.length === 2) {
                        actDate.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10), 0, 0);
                    }
                }
                return {
                    ...a,
                    startTime: actDate.toISOString(),
                };
            });
        });

        return enforceSequentialTimeline(baseActivities);
    }, [itinerary, days]);

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

        if (!disruptionActivity) return;

        try {
            // Show processing toast
            const processingToast = toast.loading('Re-optimizing itinerary with AI...');

            // Call Gemini reoptimizer via API route
            const currentActivityIndex = timelineActivities.findIndex(a => a.id === disruptionActivity.id);
            const remainingActivities = timelineActivities.slice(currentActivityIndex + 1);
            
            const response = await fetch('/api/ai/reoptimize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    issueType: type,
                    description: details || '',
                    currentActivity: {
                        time: disruptionActivity.time,
                        title: disruptionActivity.title,
                        location: disruptionActivity.location,
                        lat: disruptionActivity.lat,
                        lng: disruptionActivity.lng,
                    },
                    remainingActivities: remainingActivities.map(a => ({
                        id: a.id,
                        time: a.time,
                        title: a.title,
                        location: a.location,
                        lat: a.lat,
                        lng: a.lng,
                    })),
                    destination: destination,
                }),
            });

            const result = await response.json();

            console.log('Reoptimization result:', result);

            toast.dismiss(processingToast);

            if (result.success && result.updatedActivities && result.updatedActivities.length > 0) {
                // Apply the changes to the itinerary
                const updatedDays = [...(itinerary.itineraryDays || [])];
                
                // Update activities with AI suggestions using ID matching
                result.updatedActivities.forEach((updatedActivity: any) => {
                    // Find the activity by ID (AI should return the correct ID)
                    for (const day of updatedDays) {
                        const actIndex = day.activities.findIndex((a: any) => a.id === updatedActivity.id);
                        if (actIndex >= 0) {
                            console.log(`Updating activity ${updatedActivity.id}: ${day.activities[actIndex].title} -> ${updatedActivity.title}`);
                            updatedDays[day.dayNumber - 1].activities[actIndex] = {
                                ...day.activities[actIndex],
                                time: updatedActivity.time,
                                title: updatedActivity.title,
                                location: updatedActivity.location,
                                notes: updatedActivity.notes || day.activities[actIndex].notes,
                                status: 'upcoming' as const,
                            };
                            break;
                        }
                    }
                });

                // Don't mark current activity as issue since AI has handled it
                // Just add a note about what happened
                for (const day of updatedDays) {
                    const actIndex = day.activities.findIndex(a => a.id === disruptionActivity.id);
                    if (actIndex >= 0) {
                        updatedDays[day.dayNumber - 1].activities[actIndex] = {
                            ...day.activities[actIndex],
                            notes: `Handled: ${details || type}`,
                            // Keep status as 'upcoming' - AI has resolved the issue
                        };
                        break;
                    }
                }

                // Update the itinerary in database - keep as Active since AI resolved it
                await updateItinerary(itinerary.id, {
                    itineraryDays: updatedDays,
                    status: 'Active',
                });

                toast.success('Itinerary Updated!', {
                    description: result.message,
                    duration: 5000,
                });

                // Refresh the page to show changes
                setTimeout(() => window.location.reload(), 1500);
            } else {
                // If AI fails, just mark the activity as disrupted
                await updateActivity(disruptionActivity.id, {
                    status: 'issue',
                    notes: details || type
                });

                await updateItinerary(itinerary.id, {
                    status: 'Disrupted',
                    issueSummary: type
                });

                toast.warning('Issue Reported', {
                    description: result.message || 'Manual review may be needed.',
                    duration: 4000,
                });
            }
        } catch (error) {
            console.error("Failed to report disruption", error);
            toast.error('Failed to Report Issue', {
                description: 'Please try again or contact support.',
                duration: 4000,
            });
        }

        setDisruptionActivity(null);
    };

    // Fallback data if itineraryDays is missing (for older mocks)
    const totalDays = itinerary.totalDays || days.length;
    const origin = itinerary.from || itinerary.origin || "Origin";
    const destination = itinerary.to || itinerary.d || "Destination";

    const isTripCompleted = itinerary.status === 'Completed';
    const isDraft = itinerary.status === 'Draft';
    const isDisrupted = itinerary.status === 'Disrupted';

    return (
        <div className="min-h-screen bg-gray-50 font-sans">
            {/* Split Layout Container */}
            <div className="flex flex-col lg:flex-row h-screen overflow-hidden">

                {/* Left Panel - Scrollable Itinerary (60% on Desktop) */}
                <div className="w-full lg:w-[60%] h-full flex flex-col border-r border-gray-200 bg-[#fafafa] overflow-y-auto">
                    {/* Header */}
                    <header className="sticky top-0 z-20 bg-white/95 backdrop-blur-md border-b border-gray-200 pl-24 pr-8 py-6">
                        <div className="flex justify-between items-center mb-4">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">{itinerary.c}</h1>
                                <div className="flex items-center gap-2 text-gray-500 text-sm mt-1">
                                    <span>{origin}</span>
                                    <MapPin className="w-4 h-4 text-gray-700" />
                                    <span>{destination}</span>
                                    <span className="mx-2">•</span>
                                    <Calendar className="w-4 h-4 text-gray-700" />
                                    <span>{totalDays} Days</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-sm font-medium text-gray-900 mb-1">Trip Progress</div>
                                <TripProgressBar timeline={timelineActivities} isDraft={isDraft} />
                            </div>
                        </div>
                    </header>

                    {/* Timeline Content */}
                    <div className="pl-24 pr-8 py-8 space-y-8">
                        {days.map((day) => {
                            const dayActs = timelineActivities.filter((sa: SequentialActivity) => day.activities.some((a: any) => a.id === sa.id));
                            if (dayActs.length === 0) return null;
                            return (
                                <DayTimelineBlock
                                    key={day.id}
                                    day={day}
                                    activities={dayActs as (SequentialActivity & Activity)[]}
                                    isTripCompleted={isTripCompleted}
                                    onViewMap={(a) => setSelectedActivity(a)}
                                    onReportIssue={(a) => setDisruptionActivity(a)}
                                    itineraryIssueSummary={itinerary.issueSummary}
                                />
                            );
                        })}
                    </div>
                </div>

                {/* Right Panel — floating dashboard column (40% on Desktop) */}
                <div className="hidden lg:flex lg:w-[40%] h-full flex-col bg-[#f3f4f6] p-3 gap-3 overflow-hidden">

                    {/* Map Card */}
                    <div className="flex-[6] min-h-0 rounded-2xl overflow-hidden shadow-md bg-white">
                        <ClientMap
                            isDisrupted={isDisrupted}
                            activities={timelineActivities.map((a) => ({
                                id: a.id,
                                title: a.title,
                                time: a.time,
                                location: a.location,
                                status: a.status,
                                lat: a.lat,
                                lng: a.lng,
                                startTime: a.startTime,
                                endTime: a.endTime,
                            }))}
                            flights={(itinerary.flights || []).map((f: any) => ({
                                type: f.type,
                                airport: f.airport,
                                lat: f.lat,
                                lng: f.lng,
                                date: f.date ? new Date(f.date).toLocaleDateString() : '',
                                time: f.flightTime || ''
                            }))}
                            selectedActivity={selectedActivity}
                        />
                    </div>

                    {/* Travel Bookings Card */}
                    <div className="flex-[4] min-h-0 rounded-2xl shadow-md bg-white p-4 overflow-hidden flex flex-col">
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3.5 flex-shrink-0">Travel Bookings</p>

                        <div className="grid grid-cols-2 grid-rows-2 gap-3 auto-rows-fr flex-1 min-h-0">

                            {/* Arrival Flight */}
                            {(() => {
                                const f = (itinerary.flights || []).find((fl: any) => fl.type === 'Departure');
                                const from = origin !== 'Origin' ? origin : '—';
                                const to = destination !== 'Destination' ? destination : (f?.airport || '—');
                                return (
                                    <div className="booking-card booking-flight-arrival h-full group">
                                        <div className="flex-1 min-w-0">
                                            <div className="booking-label">
                                                <PlaneTakeoff className="w-3.5 h-3.5" />
                                                ARRIVAL FLIGHT
                                            </div>
                                            {f ? (
                                                <div className="flex flex-col">
                                                    <h4 className="booking-title truncate">{from} → {to}</h4>
                                                    <p className="booking-meta">
                                                        {f.date && new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                                                        {f.airline && ` • ${f.airline}`}
                                                    </p>
                                                </div>
                                            ) : <p className="text-xs text-gray-400 italic">Not added</p>}
                                        </div>
                                        {f && (
                                            <div className="flex flex-col items-end">
                                                <div className="booking-time">
                                                    {[f.flightTime, f.arrivalTime].filter(Boolean).join(' – ') || 'TBD'}
                                                </div>
                                                <div className="text-[10px] text-gray-400 font-bold uppercase tracking-wider mt-0.5">SCHEDULED</div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}

                            {/* Departure Flight */}
                            {(() => {
                                const f = (itinerary.flights || []).find((fl: any) => fl.type === 'Return');
                                const from = destination !== 'Destination' ? destination : (f?.airport || '—');
                                const to = origin !== 'Origin' ? origin : '—';
                                return (
                                    <div className="booking-card booking-flight-departure h-full group">
                                        <div className="flex-1 min-w-0">
                                            <div className="booking-label">
                                                <PlaneLanding className="w-3.5 h-3.5" />
                                                DEPARTURE FLIGHT
                                            </div>
                                            {f ? (
                                                <div className="flex flex-col">
                                                    <h4 className="booking-title truncate">{from} → {to}</h4>
                                                    <p className="booking-meta">
                                                        {f.date && new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                                                        {f.airline && ` • ${f.airline}`}
                                                    </p>
                                                </div>
                                            ) : <p className="text-xs text-gray-400 italic">Not added</p>}
                                        </div>
                                        {f && (
                                            <div className="flex flex-col items-end">
                                                <div className="booking-time">
                                                    {[f.flightTime, f.arrivalTime].filter(Boolean).join(' – ') || 'TBD'}
                                                </div>
                                                <div className="text-[10px] text-gray-400 font-bold uppercase tracking-wider mt-0.5">SCHEDULED</div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}

                            {/* Hotel */}
                            {(() => {
                                const stays: any[] = (itinerary.hotelStays as any[]) || [];
                                const h = stays[0] ?? null;
                                const nights = h?.checkIn && h?.checkOut
                                    ? Math.round((new Date(h.checkOut).getTime() - new Date(h.checkIn).getTime()) / 86400000)
                                    : null;
                                return (
                                    <div className="booking-card booking-hotel h-full group">
                                        <div className="flex-1 min-w-0">
                                            <div className="booking-label">
                                                <BedDouble className="w-3.5 h-3.5" />
                                                HOTEL STAY
                                            </div>
                                            {h ? (
                                                <div className="flex flex-col">
                                                    <h4 className="booking-title truncate">{h.hotelName || 'Hotel'}</h4>
                                                    <p className="booking-meta">
                                                        {h.checkIn && new Date(h.checkIn).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                                                        {stays.length > 1 && ` • +${stays.length - 1} more`}
                                                    </p>
                                                </div>
                                            ) : <p className="text-xs text-gray-400 italic">Not added</p>}
                                        </div>
                                        {h && (
                                            <div className="flex items-center gap-3">
                                                <div className="flex flex-col items-end">
                                                    <div className="booking-time">
                                                        {nights !== null ? `${nights} Night${nights !== 1 ? 's' : ''}` : 'Duration TBD'}
                                                    </div>
                                                    <div className="text-[10px] text-gray-400 font-bold uppercase tracking-wider mt-0.5">CONFIRMED</div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}

                            {/* Emergency */}
                            <div className="booking-card booking-emergency h-full group">
                                <div className="flex-1 min-w-0">
                                    <div className="booking-label text-red-600">
                                        <Asterisk className="w-3.5 h-3.5" />
                                        EMERGENCY
                                    </div>
                                    <div className="flex flex-col">
                                        <h4 className="booking-title truncate">{(itinerary as any).agentName || 'Aman Sharma'}</h4>
                                        <p className="booking-meta text-red-400 text-[11px] leading-tight mb-4">Call for urgent help</p>
                                        <Button
                                            variant="outline"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                window.location.href = `tel:${(itinerary as any).agentPhone || '+91 91234 56789'}`;
                                            }}
                                            className="booking-call-button"
                                        >
                                            <Phone className="w-3.5 h-3.5" />
                                            CALL NOW
                                        </Button>
                                    </div>
                                </div>
                            </div>

                        </div>
                    </div >
                </div >

                {/* Disruption Modal */}
                {
                    disruptionActivity && (
                        <DisruptionModal
                            isOpen={!!disruptionActivity}
                            onClose={() => setDisruptionActivity(null)}
                            onSubmit={handleDisruptionSubmit}
                            activityTitle={disruptionActivity?.title || ''}
                        />
                    )
                }
            </div >
        </div >
    );
}
