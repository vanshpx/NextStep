"use client";

import { useState, use } from 'react';
import { motion } from 'framer-motion';
import { MapPin, Calendar, AlertTriangle, PlaneTakeoff, PlaneLanding, BedDouble, Phone } from 'lucide-react';
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

    const isTripCompleted = itinerary.status === 'Completed';
    const isDraft = itinerary.status === 'Draft';

    // Progress: completed activities ÷ total activities
    // Draft → always 0%. Active/Upcoming → 0% until activities are marked completed.
    const allActivities = days.flatMap(d => d.activities);
    const completedCount = allActivities.filter(a => a.status === 'completed').length;
    const totalCount = allActivities.length;
    const progress = isDraft || totalCount === 0
        ? 0
        : isTripCompleted
            ? 100
            : Math.round((completedCount / totalCount) * 100);

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
                        {/* Derive which activity is "current" from real data:
                            - 0 completed  → no current (not started)
                            - some completed, some not → first non-completed is current
                            - all completed → no current (finished) */}
                        {(() => {
                            const flatActivities = days.flatMap(d => d.activities);
                            const completedIds = new Set(flatActivities.filter(a => a.status === 'completed').map(a => a.id));
                            const currentActivity = completedIds.size > 0 && completedIds.size < flatActivities.length
                                ? flatActivities.find(a => !completedIds.has(a.id))
                                : null;
                            const currentActivityId = currentActivity?.id ?? null;

                            return days.map((day) => {
                                // Day status derived from activities
                                const dayActs = day.activities;
                                const dayAllCompleted = dayActs.length > 0 && dayActs.every(a => a.status === 'completed');
                                const dayHasCurrent = dayActs.some(a => a.id === currentActivityId);
                                const isCompleted = isTripCompleted || dayAllCompleted;
                                const isActive = !isCompleted && dayHasCurrent;

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

                                            {day.activities.map((activity) => {
                                                // Use real stored status — no mock overrides
                                                const isActCompleted = activity.status === 'completed';
                                                const isActCurrent = activity.id === currentActivityId;

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
                            });
                        })()} {/* end IIFE */}
                    </div>
                </div>

                {/* Right Panel — floating dashboard column */}
                <div className="hidden lg:flex w-1/2 h-full flex-col bg-gray-100 p-3 gap-3 overflow-hidden">

                    {/* Map Card */}
                    <div className="flex-[6] min-h-0 rounded-2xl overflow-hidden shadow-md bg-white">
                        <ClientMap
                            activities={days.flatMap(d => d.activities).map((a: any) => ({
                                id: a.id,
                                title: a.title,
                                time: a.time,
                                location: a.location,
                                status: a.status,
                                lat: a.lat,
                                lng: a.lng,
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
                    <div className="flex-[4] min-h-0 rounded-2xl shadow-md bg-white p-3.5 overflow-hidden flex flex-col">
                        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-2.5 flex-shrink-0">Travel Bookings</p>

                        <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">

                            {/* TOP-LEFT: Arrival Flight */}
                            {(() => {
                                const f = (itinerary.flights || []).find((fl: any) => fl.type === 'Departure');
                                const from = origin !== 'Origin' ? origin : '—';
                                const to = destination !== 'Destination' ? destination : (f?.airport || '—');
                                return (
                                    <div className="bg-gray-50 rounded-xl border border-gray-100 shadow-sm p-3.5 flex flex-col gap-1.5 border-l-[3px] border-l-blue-400 overflow-hidden">
                                        <div className="flex items-center gap-1.5">
                                            <PlaneTakeoff className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                                            <span className="text-[11px] font-semibold text-blue-500 uppercase tracking-wider">Arrival Flight</span>
                                        </div>
                                        {f ? (<>
                                            <p className="text-[15px] font-bold text-gray-900 truncate leading-snug">{from} → {to}</p>
                                            {f.date && <p className="text-xs text-gray-500">{new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>}
                                            {(f.airline || f.flightNumber) && <p className="text-xs text-gray-500 truncate">{[f.airline, f.flightNumber].filter(Boolean).join(' • ')}</p>}
                                            {(f.flightTime || f.arrivalTime) && <p className="text-sm font-semibold text-blue-600">{[f.flightTime, f.arrivalTime].filter(Boolean).join(' – ')}</p>}
                                        </>) : <p className="text-xs text-gray-400 italic mt-auto">Not added</p>}
                                    </div>
                                );
                            })()}

                            {/* TOP-RIGHT: Return / Departure Flight */}
                            {(() => {
                                const f = (itinerary.flights || []).find((fl: any) => fl.type === 'Return');
                                const from = destination !== 'Destination' ? destination : (f?.airport || '—');
                                const to = origin !== 'Origin' ? origin : '—';
                                return (
                                    <div className="bg-gray-50 rounded-xl border border-gray-100 shadow-sm p-3.5 flex flex-col gap-1.5 border-l-[3px] border-l-violet-400 overflow-hidden">
                                        <div className="flex items-center gap-1.5">
                                            <PlaneLanding className="w-3.5 h-3.5 text-violet-400 flex-shrink-0" />
                                            <span className="text-[11px] font-semibold text-violet-500 uppercase tracking-wider">Departure Flight</span>
                                        </div>
                                        {f ? (<>
                                            <p className="text-[15px] font-bold text-gray-900 truncate leading-snug">{from} → {to}</p>
                                            {f.date && <p className="text-xs text-gray-500">{new Date(f.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>}
                                            {(f.airline || f.flightNumber) && <p className="text-xs text-gray-500 truncate">{[f.airline, f.flightNumber].filter(Boolean).join(' • ')}</p>}
                                            {(f.flightTime || f.arrivalTime) && <p className="text-sm font-semibold text-violet-600">{[f.flightTime, f.arrivalTime].filter(Boolean).join(' – ')}</p>}
                                        </>) : <p className="text-xs text-gray-400 italic mt-auto">Not added</p>}
                                    </div>
                                );
                            })()}

                            {/* BOTTOM-LEFT: Hotel */}
                            {(() => {
                                const stays: any[] = (itinerary.hotelStays as any[]) || [];
                                const h = stays[0] ?? null;
                                const extra = stays.length - 1;
                                const nights = h?.checkIn && h?.checkOut
                                    ? Math.round((new Date(h.checkOut).getTime() - new Date(h.checkIn).getTime()) / 86400000)
                                    : null;
                                return (
                                    <div className="bg-gray-50 rounded-xl border border-gray-100 shadow-sm p-3.5 flex flex-col gap-1.5 border-l-[3px] border-l-emerald-400 overflow-hidden">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-1.5">
                                                <BedDouble className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                                <span className="text-[11px] font-semibold text-emerald-500 uppercase tracking-wider">Hotel Stay</span>
                                            </div>
                                            {extra > 0 && <span className="text-[11px] text-emerald-600 font-medium">+{extra} more</span>}
                                        </div>
                                        {h ? (<>
                                            <p className="text-[15px] font-bold text-gray-900 truncate leading-snug">{h.hotelName || 'Hotel'}</p>
                                            {h.checkIn && <p className="text-xs text-gray-500">Check-in: {new Date(h.checkIn).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>}
                                            {nights !== null && <p className="text-sm font-semibold text-emerald-600">{nights} night{nights !== 1 ? 's' : ''}</p>}
                                        </>) : <p className="text-xs text-gray-400 italic mt-auto">Not added</p>}
                                    </div>
                                );
                            })()}

                            {/* BOTTOM-RIGHT: Emergency */}
                            <div className="bg-gray-50 rounded-xl border border-gray-100 shadow-sm p-3.5 flex flex-col gap-1.5 border-l-[3px] border-l-red-400 overflow-hidden">
                                <div className="flex items-center gap-1.5">
                                    <Phone className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                                    <span className="text-[11px] font-semibold text-red-500 uppercase tracking-wider">Emergency</span>
                                </div>
                                <p className="text-[15px] font-bold text-gray-900 truncate leading-snug">
                                    {(itinerary as any).agentName || 'Travel Agent'}
                                </p>
                                <p className="text-xs text-gray-400">For urgent help, call your agent</p>
                                {(itinerary as any).agentPhone
                                    ? <a href={`tel:${(itinerary as any).agentPhone}`} className="text-sm font-bold text-red-500 hover:text-red-600 mt-auto inline-flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{(itinerary as any).agentPhone}</a>
                                    : <p className="text-xs text-gray-400 italic mt-auto">Contact not added</p>
                                }
                            </div>

                        </div>
                    </div>
                </div>

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
