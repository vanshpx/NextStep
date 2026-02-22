"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/Button";
import ActivityBlock from "@/components/builder/ActivityBlock";
import { Plus, Trash } from "lucide-react";

const generateId = () => Date.now() + Math.floor(Math.random() * 10000);

import { Stay } from "@/components/builder/HotelStays";

import { Activity } from "@/context/ItineraryContext";

export interface Day {
    id: number;
    activities: Activity[];
}

interface DayBuilderProps {
    days: Day[];
    onChange: (days: Day[]) => void;
    startDate?: string;
    stays?: Stay[];
    isActive?: boolean;
    isCompleted?: boolean;
}

export default function DayBuilder({ days, onChange, startDate, stays = [], isActive = false, isCompleted = false }: DayBuilderProps) {
    const addDay = () => {
        onChange([...days, { id: generateId(), activities: [] }]);
    };

    const removeDay = (id: number) => {
        if (days.length > 1) {
            onChange(days.filter(d => d.id !== id));
        }
    };

    const addActivity = (dayIndex: number) => {
        const newDays = [...days];
        const newActivity: Activity = {
            id: generateId(),
            time: "",
            duration: 1, // Default 1 hour
            title: "",
            location: "",
            notes: "",
            status: 'upcoming'
        };
        newDays[dayIndex] = {
            ...newDays[dayIndex],
            activities: [...newDays[dayIndex].activities, newActivity]
        };
        onChange(newDays);
    };

    const removeActivity = (dayIndex: number, activityId: number) => {
        const newDays = [...days];
        newDays[dayIndex] = {
            ...newDays[dayIndex],
            activities: newDays[dayIndex].activities.filter(a => a.id !== activityId)
        };
        onChange(newDays);
    };

    const updateActivity = (dayIndex: number, activityId: number, updates: Partial<Activity>) => {
        const newDays = [...days];
        newDays[dayIndex] = {
            ...newDays[dayIndex],
            activities: newDays[dayIndex].activities.map(a =>
                a.id === activityId ? { ...a, ...updates } : a
            )
        };
        onChange(newDays);
    };

    const isActivityLocked = (dayIndex: number, activity: Activity) => {
        if (isCompleted) return true;

        // User requested to UNLOCK activities for active itineraries.
        // All activities are editable unless the itinerary is strictly Completed.
        return false;
    };

    const getDayInfo = (index: number) => {
        if (!startDate) return null;

        const date = new Date(startDate);
        date.setDate(date.getDate() + index);

        // Format date string for display (e.g., "Mon, Jan 1")
        const dateStr = date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

        // Find hotel for this date
        // Simple logic: if date is >= checkIn and < checkOut (standard hotel logic usually counts nights)
        // Adjusting: checking if date string matches range
        // Standardization required for comparison, using simplistic string compare for ISO YYYY-MM-DD
        const isoDate = date.toISOString().split('T')[0];

        const stay = stays.find(s => {
            if (!s.checkIn || !s.checkOut) return false;
            return isoDate >= s.checkIn && isoDate < s.checkOut;
        });

        return { dateStr, hotel: stay?.hotelName };
    };

    return (
        <div className="space-y-8">
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                    Itinerary Schedule
                </h2>
            </div>

            <div className="space-y-6">
                <AnimatePresence>
                    {days.map((day, dayIndex) => {
                        const dayInfo = getDayInfo(dayIndex);

                        return (
                            <motion.div
                                key={day.id}
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: "auto" }}
                                exit={{ opacity: 0, height: 0 }}
                                className="bg-gray-50 rounded-xl border border-gray-200 overflow-hidden shadow-sm"
                            >
                                <div className="bg-white px-6 py-4 flex justify-between items-center border-b border-gray-200">
                                    <div>
                                        <h3 className="font-bold text-lg text-primary-700 flex items-center gap-3">
                                            Day {dayIndex + 1}
                                            {dayInfo && <span className="text-sm font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-md">{dayInfo.dateStr}</span>}
                                        </h3>
                                        {dayInfo?.hotel && (
                                            <div className="text-xs text-primary-600 font-medium mt-1 flex items-center gap-1">
                                                🏨 Staying at: {dayInfo.hotel}
                                            </div>
                                        )}
                                    </div>
                                    {days.length > 1 && !isCompleted && (
                                        <Button variant="ghost" size="sm" onClick={() => removeDay(day.id)} className="text-red-500 hover:bg-red-50 hover:text-red-700">
                                            <Trash className="w-4 h-4 mr-2" />
                                            Remove Day
                                        </Button>
                                    )}
                                </div>

                                <div className="p-6 space-y-4">
                                    {day.activities.map((activity) => {
                                        // Calculate if activity is locked
                                        const isLocked = isActivityLocked(dayIndex, activity);

                                        return (
                                            <ActivityBlock
                                                key={activity.id}
                                                activity={activity}
                                                onUpdate={(updates) => updateActivity(dayIndex, activity.id, updates)}
                                                onRemove={() => removeActivity(dayIndex, activity.id)}
                                                readOnly={isLocked}
                                            />
                                        );
                                    })}

                                    {!isCompleted && (
                                        <Button variant="outline" onClick={() => addActivity(dayIndex)} className="w-full border-dashed border-gray-300 hover:border-primary-500 hover:text-primary-600 hover:bg-primary-50/50">
                                            <Plus className="w-4 h-4 mr-2" />
                                            Add Activity
                                        </Button>
                                    )}
                                </div>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>
            </div>

            {!isCompleted && (
                <Button
                    onClick={addDay}
                    size="lg"
                    variant="secondary"
                    className="w-full py-6 text-base font-semibold bg-white text-gray-900 border-black hover:bg-gray-50 shadow-sm transition-all"
                >
                    <Plus className="w-5 h-5 mr-2" />
                    Add Another Day
                </Button>
            )}
        </div>
    );
}
