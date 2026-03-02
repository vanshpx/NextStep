"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { toast } from "sonner";

export interface Activity {
    id: number;
    time: string;
    duration?: number;
    title: string;
    location: string;
    notes: string | null;
    status: 'completed' | 'current' | 'upcoming' | 'issue';
    lat?: number;
    lng?: number;
}

export interface Day {
    id: number;
    dayNumber: number;
    activities: Activity[];
}

// Define the Itinerary type (matching what we have in mock data)
export interface Itinerary {
    id: number;
    c: string; // client name
    d: string;
    displayPrice?: string;

    // New fields for details (stored as relations)
    flights?: Flight[];
    hotelStays?: HotelStay[];

    status: 'Draft' | 'Upcoming' | 'Active' | 'Completed' | 'Disrupted'; // status
    date: string; // date range
    activities?: unknown[]; // Legacy field, keeping for now
    // New fields for detailed view
    age?: number;
    days?: number;
    email?: string;
    mobile?: string;
    origin?: string;

    // Detailed Itinerary Data
    from?: string; // Origin City
    to?: string;   // Destination City
    totalDays?: number;
    itineraryDays?: Day[]; // The full schedule
    agentName?: string;
    agentPhone?: string;
    issueSummary?: string;
}

export interface Flight {
    id: number;
    type: string; // 'Departure' | 'Return'
    date?: string;
    airline?: string;
    flightNumber?: string;
    flightTime?: string;
    arrivalTime?: string;
    airport?: string;
    lat?: number;
    lng?: number;
}

export interface HotelStay {
    id: number;
    hotelName: string;
    checkIn?: string;
    checkOut?: string;
    notes?: string;
    lat?: number;
    lng?: number;
}

interface ItineraryContextType {
    itineraries: Itinerary[];
    isLoading: boolean;
    addItinerary: (itinerary: Omit<Itinerary, 'id'>) => Promise<void>;
    updateActivity: (activityId: number, updates: Partial<Activity>) => Promise<void>;
    updateItinerary: (id: number, itinerary: Partial<Itinerary>) => Promise<void>;
    deleteItinerary: (id: number) => Promise<void>;
    getItinerary: (id: number) => Itinerary | undefined;
    refreshItineraries: () => Promise<void>;
    searchQuery: string;
    setSearchQuery: (query: string) => void;
}

const ItineraryContext = createContext<ItineraryContextType | undefined>(undefined);

export function ItineraryProvider({ children }: { children: ReactNode }) {
    const [itineraries, setItineraries] = useState<Itinerary[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");

    const fetchItineraries = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/itineraries', { cache: 'no-store' });
            if (response.ok) {
                const data = await response.json();

                // Auto-transition 'Upcoming' to 'Active' if start date is reached
                const now = new Date();
                const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

                const updatedData = await Promise.all(data.map(async (itinerary: Itinerary) => {
                    if (itinerary.status === 'Upcoming' && itinerary.flights && itinerary.flights.length > 0) {
                        let startDate: Date | null = null;

                        // Find departure flight
                        const departureFlight = itinerary.flights.find(f => f.type === 'Departure');
                        if (departureFlight && departureFlight.date) {
                            startDate = new Date(departureFlight.date);
                            startDate.setHours(0, 0, 0, 0);
                        }

                        if (startDate && startDate <= today) {
                            console.log(`Auto-activating itinerary ${itinerary.id} - Start: ${startDate}, Today: ${today}`);
                            // Optimistic update locally
                            itinerary.status = 'Active';

                            // Fire and forget update to server
                            fetch(`/api/itineraries/${itinerary.id}`, {
                                method: 'PATCH',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ status: 'Active' })
                            });
                        }
                    }

                    // Add Active/Disrupted → Completed transition logic
                    if ((itinerary.status === 'Active' || itinerary.status === 'Disrupted')) {
                        let shouldComplete = false;

                        // Check if all activities are completed (based on time)
                        if (itinerary.itineraryDays && itinerary.itineraryDays.length > 0) {
                            const allActivities = itinerary.itineraryDays.flatMap(day => day.activities || []);
                            
                            if (allActivities.length > 0) {
                                // Get the last activity's end time
                                const lastDay = itinerary.itineraryDays[itinerary.itineraryDays.length - 1];
                                const lastActivity = lastDay.activities?.[lastDay.activities.length - 1];
                                
                                if (lastActivity && lastActivity.time) {
                                    // Calculate when the last activity ends (start time + 2 hours)
                                    const startDateRaw = itinerary.flights?.find((f: any) => f.type === 'Departure')?.date || new Date().toISOString();
                                    const startDate = new Date(startDateRaw);
                                    const lastActivityDate = new Date(startDate);
                                    lastActivityDate.setDate(lastActivityDate.getDate() + (lastDay.dayNumber - 1));
                                    
                                    const timeParts = lastActivity.time.split(':');
                                    if (timeParts.length === 2) {
                                        lastActivityDate.setHours(parseInt(timeParts[0], 10), parseInt(timeParts[1], 10), 0, 0);
                                    }
                                    
                                    // Add 2 hours for last activity duration
                                    const lastActivityEndTime = new Date(lastActivityDate.getTime() + (2 * 60 * 60 * 1000));
                                    
                                    // If last activity has ended, complete the itinerary
                                    if (now >= lastActivityEndTime) {
                                        shouldComplete = true;
                                    }
                                }
                            }
                        }
                        
                        // Fallback: check return flight date
                        if (!shouldComplete && itinerary.flights && itinerary.flights.length > 0) {
                            const returnFlight = itinerary.flights.find(f => f.type === 'Return');
                            if (returnFlight && returnFlight.date) {
                                const endDate = new Date(returnFlight.date);
                                endDate.setHours(23, 59, 59, 999); // End of return flight day
                                
                                if (now >= endDate) {
                                    shouldComplete = true;
                                }
                            }
                        }

                        if (shouldComplete) {
                            console.log(`Auto-completing itinerary ${itinerary.id}`);
                            // Optimistic update locally
                            itinerary.status = 'Completed';

                            // Show completion notification
                            toast.success(`Trip Completed: ${itinerary.c}`, {
                                description: `The trip to ${itinerary.d} has been completed.`,
                                duration: 5000,
                            });

                            // Fire and forget update to server
                            fetch(`/api/itineraries/${itinerary.id}`, {
                                method: 'PATCH',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ status: 'Completed' })
                            });
                        }
                    }

                    return itinerary;
                }));

                setItineraries(updatedData);
            } else {
                console.error('Failed to fetch itineraries');
            }
        } catch (error) {
            console.error('Error fetching itineraries:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchItineraries();
        
        // Set up periodic refresh every 60 seconds to catch status transitions
        const intervalId = setInterval(() => {
            fetchItineraries();
        }, 60000); // 60 seconds
        
        return () => clearInterval(intervalId);
    }, []);

    const addItinerary = async (newItinerary: Omit<Itinerary, 'id'>) => {
        try {
            const response = await fetch('/api/itineraries', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(newItinerary),
            });

            if (response.ok) {
                const createdItinerary = await response.json();
                setItineraries(prev => [createdItinerary, ...prev]);
            } else {
                console.error('Failed to create itinerary');
            }
        } catch (error) {
            console.error('Error creating itinerary:', error);
        }
    };

    const updateItinerary = async (id: number, updatedItinerary: Partial<Itinerary>) => {
        try {
            const response = await fetch(`/api/itineraries/${id}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(updatedItinerary),
            });

            if (response.ok) {
                const result = await response.json();
                setItineraries(prev => prev.map(item => item.id === id ? result : item));
            } else {
                console.error('Failed to update itinerary');
            }
        } catch (error) {
            console.error('Error updating itinerary:', error);
        }
    };

    const deleteItinerary = async (id: number) => {
        try {
            const response = await fetch(`/api/itineraries/${id}`, {
                method: 'DELETE',
            });

            if (response.ok) {
                setItineraries(prev => prev.filter(item => item.id !== id));
            } else {
                console.error('Failed to delete itinerary');
            }
        } catch (error) {
            console.error('Error deleting itinerary:', error);
        }
    };

    const getItinerary = (id: number) => {
        return itineraries.find(i => i.id === id);
    };

    const updateActivity = async (activityId: number, updates: Partial<Activity>) => {
        try {
            const response = await fetch(`/api/activities/${activityId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(updates),
            });

            if (response.ok) {
                // Refresh itineraries to get updated activity
                await fetchItineraries();
            } else {
                console.error('Failed to update activity');
            }
        } catch (error) {
            console.error('Error updating activity:', error);
        }
    };

    return (
        <ItineraryContext.Provider value={{
            itineraries, isLoading, addItinerary, updateItinerary, deleteItinerary, getItinerary, updateActivity, refreshItineraries: fetchItineraries, searchQuery, setSearchQuery
        }}>
            {children}
        </ItineraryContext.Provider>
    );
}

export function useItinerary() {
    const context = useContext(ItineraryContext);
    if (context === undefined) {
        throw new Error("useItinerary must be used within an ItineraryProvider");
    }
    return context;
}
