"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

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
    updateItinerary: (id: number, itinerary: Partial<Itinerary>) => Promise<void>;
    deleteItinerary: (id: number) => Promise<void>;
    getItinerary: (id: number) => Itinerary | undefined;
    refreshItineraries: () => Promise<void>;
}

const ItineraryContext = createContext<ItineraryContextType | undefined>(undefined);

export function ItineraryProvider({ children }: { children: ReactNode }) {
    const [itineraries, setItineraries] = useState<Itinerary[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchItineraries = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/itineraries', { cache: 'no-store' });
            if (response.ok) {
                const data = await response.json();

                // Auto-transition 'Upcoming' to 'Active' if start date is reached
                const today = new Date();
                today.setHours(0, 0, 0, 0);

                const updatedData = await Promise.all(data.map(async (itinerary: Itinerary) => {
                    if (itinerary.status === 'Upcoming' && itinerary.flights && itinerary.flights.length > 0) {
                        let startDate: Date | null = null;

                        // Find departure flight
                        const departureFlight = itinerary.flights.find(f => f.type === 'Departure');
                        if (departureFlight && departureFlight.date) {
                            startDate = new Date(departureFlight.date);
                        }

                        if (startDate && startDate <= today) {
                            console.log(`Auto-activating itinerary ${itinerary.id}`);
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

    return (
        <ItineraryContext.Provider value={{ itineraries, isLoading, addItinerary, updateItinerary, deleteItinerary, getItinerary, refreshItineraries: fetchItineraries }}>
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
