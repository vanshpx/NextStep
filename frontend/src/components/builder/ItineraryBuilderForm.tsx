"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useItinerary, Itinerary } from "@/context/ItineraryContext";

import ClientDetailsForm from "@/components/builder/ClientDetailsForm";
import TravelDetails from "@/components/builder/TravelDetails";
import HotelStays, { Stay } from "@/components/builder/HotelStays";
import DayBuilder, { Day } from "@/components/builder/DayBuilder";
import { Button } from "@/components/ui/Button";
import { Save, Send } from "lucide-react";

interface ItineraryBuilderFormProps {
    initialData?: Itinerary;
    isEditing?: boolean;
}

export default function ItineraryBuilderForm({ initialData, isEditing = false }: ItineraryBuilderFormProps) {
    const router = useRouter();
    const { addItinerary, updateItinerary } = useItinerary();

    // --- State Management ---
    const [clientDetails, setClientDetails] = useState({
        clientName: initialData?.c || "",
        age: initialData?.age ? initialData.age.toString() : "",
        contact: initialData?.mobile || "",
        origin: initialData?.origin || "",
        destination: initialData?.d || "",
        days: initialData?.days ? initialData.days.toString() : ""
    });

    // Sync ALL form state when the itinerary id changes (covers the case where
    // the Context hasn't loaded yet when the component first mounts, which
    // would otherwise leave travelDetails/stays/days empty and overwrite the
    // real data in the DB the next time the user saves).
    useEffect(() => {
        if (!initialData) return;

        setClientDetails({
            clientName: initialData.c || "",
            age: initialData.age ? initialData.age.toString() : "",
            contact: initialData.mobile || "",
            origin: initialData.origin || "",
            destination: initialData.d || "",
            days: initialData.days ? initialData.days.toString() : ""
        });

        // Sync travel details / flights
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const legacyData = initialData as any;
        if (legacyData.travelDetails) {
            try {
                const parsed = typeof legacyData.travelDetails === 'string'
                    ? JSON.parse(legacyData.travelDetails)
                    : legacyData.travelDetails;
                setTravelDetails({
                    departure: parsed.departure || { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" },
                    returnTrip: parsed.returnTrip || { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" }
                });
            } catch { /* ignore bad JSON */ }
        } else if (initialData.flights && initialData.flights.length > 0) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const dep = initialData.flights.find((f: any) => f.type === 'Departure');
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const ret = initialData.flights.find((f: any) => f.type === 'Return');
            setTravelDetails({
                departure: dep
                    ? { ...dep, date: dep.date ? new Date(dep.date).toISOString().split('T')[0] : "" }
                    : { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" },
                returnTrip: ret
                    ? { ...ret, date: ret.date ? new Date(ret.date).toISOString().split('T')[0] : "" }
                    : { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" }
            });
        } else {
            setTravelDetails({
                departure: { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "", lat: undefined, lng: undefined },
                returnTrip: { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "", lat: undefined, lng: undefined }
            });
        }

        // Sync hotel stays
        if (legacyData.hotelDetails) {
            try {
                const parsed = typeof legacyData.hotelDetails === 'string' ? JSON.parse(legacyData.hotelDetails) : legacyData.hotelDetails;
                if (Array.isArray(parsed)) { setStays(parsed); }
            } catch { /* ignore */ }
        } else if (initialData.hotelStays && initialData.hotelStays.length > 0) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            setStays(initialData.hotelStays.map((h: any) => ({
                ...h,
                checkIn: h.checkIn ? new Date(h.checkIn).toISOString().split('T')[0] : "",
                checkOut: h.checkOut ? new Date(h.checkOut).toISOString().split('T')[0] : ""
            })));
        } else {
            setStays([]);
        }

        // Sync itinerary days
        if (initialData.itineraryDays && initialData.itineraryDays.length > 0) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            setDays(initialData.itineraryDays.map((d: any) => ({
                id: d.id,
                activities: d.activities || []
            })));
        } else {
            setDays([{ id: 1, activities: [] }]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialData?.id]);

    const [travelDetails, setTravelDetails] = useState(() => {
        if (initialData) {
            // Fallback for old JSON data
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const legacyData = initialData as any;
            if (legacyData.travelDetails) {
                try {
                    const parsed = typeof legacyData.travelDetails === 'string'
                        ? JSON.parse(legacyData.travelDetails)
                        : legacyData.travelDetails;
                    return {
                        departure: parsed.departure || { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" },
                        returnTrip: parsed.returnTrip || { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" }
                    };
                } catch {
                    // ignore
                }
            }
            // New strict Flights relation check
            if (initialData.flights && initialData.flights.length > 0) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const dep = initialData.flights.find((f: any) => f.type === 'Departure');
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const ret = initialData.flights.find((f: any) => f.type === 'Return');
                return {
                    departure: dep ? { ...dep, date: dep.date ? new Date(dep.date).toISOString().split('T')[0] : "" } : { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" },
                    returnTrip: ret ? { ...ret, date: ret.date ? new Date(ret.date).toISOString().split('T')[0] : "" } : { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "" }
                };
            }
        }
        return {
            departure: { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "", lat: undefined as number | undefined, lng: undefined as number | undefined },
            returnTrip: { date: "", airport: "", airline: "", flightNumber: "", departureTime: "", arrivalTime: "", lat: undefined as number | undefined, lng: undefined as number | undefined }
        };
    });

    const [stays, setStays] = useState<Stay[]>(() => {
        if (initialData) {
            // Fallback for old JSON
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const legacyData = initialData as any;
            if (legacyData.hotelDetails) {
                try {
                    const parsed = typeof legacyData.hotelDetails === 'string' ? JSON.parse(legacyData.hotelDetails) : legacyData.hotelDetails;
                    if (Array.isArray(parsed)) return parsed;
                } catch { /* ignore */ }
            }
            if (initialData.hotelStays && initialData.hotelStays.length > 0) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                return initialData.hotelStays.map((h: any) => ({
                    ...h,
                    checkIn: h.checkIn ? new Date(h.checkIn).toISOString().split('T')[0] : "",
                    checkOut: h.checkOut ? new Date(h.checkOut).toISOString().split('T')[0] : ""
                }));
            }
        }
        return [];
    });

    // Initial Day State
    const [days, setDays] = useState<Day[]>(() => {
        if (initialData?.itineraryDays && initialData.itineraryDays.length > 0) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return initialData.itineraryDays.map((d: any) => ({
                id: d.id,
                activities: d.activities || []
            }));
        }
        return [{ id: 1, activities: [] }];
    });



    // ... (rest of component)

    // Sync days count effect removed to avoid cascading renders.
    // Instead, we update clientDetails.days whenever we update the days array (e.g. in addDay/removeDay via a handler).

    // Status Checks
    const isCompleted = initialData?.status === 'Completed';
    const isActive = initialData?.status === 'Active';
    const isUpcoming = initialData?.status === 'Upcoming';

    // Conditional Logic for "Middle Stage"
    const isDeparturePassed = isActive || (() => {
        if (!travelDetails.departure.date) return false;
        const date = new Date(travelDetails.departure.date);
        // If has time, add it
        if (travelDetails.departure.arrivalTime) {
            const [h, m] = travelDetails.departure.arrivalTime.split(':').map(Number);
            date.setHours(h, m);
        }
        return date < new Date();
    })();

    const isReturnPassed = false; // Always editable as per request


    // --- Handlers ---
    const handleClientChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        setClientDetails(prev => ({ ...prev, [name]: value }));

        if (name === 'days') {
            const count = parseInt(value);
            if (!isNaN(count) && count > 0) {
                setDays(prev => {
                    const currentCount = prev.length;
                    if (count > currentCount) {
                        const newDays = [...prev];
                        for (let i = currentCount; i < count; i++) {
                            newDays.push({ id: Date.now() + i + Math.floor(Math.random() * 1000), activities: [] });
                        }
                        return newDays;
                    } else if (count < currentCount) {
                        return prev.slice(0, count);
                    }
                    return prev;
                });
            }
        }
    };

    // Auto-schedule logic when travel details change
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handleTravelChange = (type: 'departure' | 'return', field: string, value: any) => {
        setTravelDetails(prev => {
            const updated = {
                ...prev,
                [type === 'departure' ? 'departure' : 'returnTrip']: {
                    ...prev[type === 'departure' ? 'departure' : 'returnTrip'],
                    [field]: value
                }
            };

            const newDays = [...days];

            // 1. Arrival Logic (Day 1)
            // Use arrivalAirport if available, otherwise fallback to airport (origin) which is wrong but fallback
            const targetAirport = updated.departure.arrivalAirport || updated.departure.airport;
            const targetLat = updated.departure.arrivalLat ?? updated.departure.lat;
            const targetLng = updated.departure.arrivalLng ?? updated.departure.lng;

            if (targetAirport && updated.departure.arrivalTime) {
                const day1 = newDays[0];
                if (day1) {
                    const hasArrival = day1.activities.some(a => a.title.startsWith("Arrival at"));
                    if (!hasArrival) {
                        day1.activities.unshift({
                            id: Date.now() + Math.floor(Math.random() * 1000),
                            time: updated.departure.arrivalTime,
                            duration: 0.5,
                            title: `Arrival at ${targetAirport}`,
                            location: targetAirport,
                            notes: `Flight: ${updated.departure.airline} ${updated.departure.flightNumber}`,
                            lat: targetLat,
                            lng: targetLng,
                            status: 'upcoming'
                        });

                        day1.activities.splice(1, 0, {
                            id: Date.now() + Math.floor(Math.random() * 1000) + 1,
                            time: addMinutes(updated.departure.arrivalTime, 30),
                            duration: 1,
                            title: "Transfer to Hotel",
                            location: "Hotel",
                            notes: "Private Transfer arranged",
                            status: 'upcoming'
                        });
                    }
                }
            }

            // 2. Departure Logic (Last Day)
            if (updated.returnTrip.airport && updated.returnTrip.departureTime) {
                const lastDayIndex = newDays.length - 1;
                const lastDay = newDays[lastDayIndex];
                if (lastDay) {
                    const hasDeparture = lastDay.activities.some(a => a.title.startsWith("Departure from"));
                    if (!hasDeparture) {
                        const depTime = subtractMinutes(updated.returnTrip.departureTime, 180);
                        lastDay.activities.push({
                            id: Date.now() + Math.floor(Math.random() * 1000) + 2,
                            time: depTime,
                            duration: 0.5,
                            title: `Departure from ${updated.returnTrip.airport}`,
                            location: updated.returnTrip.airport,
                            notes: `Flight: ${updated.returnTrip.airline} ${updated.returnTrip.flightNumber}`,
                            lat: updated.returnTrip.lat,
                            lng: updated.returnTrip.lng,
                            status: 'upcoming'
                        });
                    }
                }
            }

            setDays(newDays);
            return updated;
        });
    };

    const addMinutes = (time: string, minutes: number) => {
        if (!time) return "";
        const [h, m] = time.split(':').map(Number);
        const date = new Date();
        date.setHours(h);
        date.setMinutes(m + minutes);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    };

    const subtractMinutes = (time: string, minutes: number) => {
        if (!time) return "";
        const [h, m] = time.split(':').map(Number);
        const date = new Date();
        date.setHours(h);
        date.setMinutes(m - minutes);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    };

    const handleSave = async (status: 'Draft' | 'Active') => {
        if (!clientDetails.clientName || !clientDetails.destination) {
            alert("Please fill in at least Client Name and Destination");
            return;
        }

        if (parseInt(clientDetails.days) <= 0) {
            alert("Number of days must be positive");
            return;
        }

        // Determine status: Finalize always defaults to 'Upcoming'.
        // Only switch to 'Active' if the departure date has already passed
        // (trip has already started). Never mutate Upcoming/Disrupted.
        let finalStatus: Itinerary['status'] = status;

        if (isEditing && isUpcoming) {
            finalStatus = 'Upcoming';
        } else if (isEditing && initialData?.status === 'Disrupted') {
            finalStatus = 'Active';
        } else if (status === 'Active') {
            // Default to Upcoming — only keep Active if departure already passed
            finalStatus = 'Upcoming';
            if (travelDetails.departure.date) {
                const startDate = new Date(travelDetails.departure.date);
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                if (startDate <= today) {
                    finalStatus = 'Active';
                }
            }
        }

        // Construct Flights Array
        const flights = [];
        if (travelDetails.departure.date || travelDetails.departure.airport || travelDetails.departure.arrivalAirport) {
            flights.push({
                type: 'Departure',
                date: travelDetails.departure.date,
                airport: travelDetails.departure.airport,
                airline: travelDetails.departure.airline,
                flightNumber: travelDetails.departure.flightNumber,
                flightTime: travelDetails.departure.departureTime,
                arrivalTime: travelDetails.departure.arrivalTime,
                lat: travelDetails.departure.lat,
                lng: travelDetails.departure.lng
            });
        }
        if (travelDetails.returnTrip.date || travelDetails.returnTrip.airport) {
            flights.push({
                type: 'Return',
                date: travelDetails.returnTrip.date,
                airport: travelDetails.returnTrip.airport,
                airline: travelDetails.returnTrip.airline,
                flightNumber: travelDetails.returnTrip.flightNumber,
                flightTime: travelDetails.returnTrip.departureTime,
                arrivalTime: travelDetails.returnTrip.arrivalTime,
                lat: travelDetails.returnTrip.lat,
                lng: travelDetails.returnTrip.lng
            });
        }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const newItinerary: any = {
            c: clientDetails.clientName,
            d: clientDetails.destination,
            s: finalStatus,
            date: travelDetails.departure.date && travelDetails.returnTrip.date
                ? `${new Date(travelDetails.departure.date).toLocaleString('default', { month: 'short', day: 'numeric' })} - ${new Date(travelDetails.returnTrip.date).toLocaleString('default', { month: 'short', day: 'numeric' })}`
                : initialData?.date || 'Upcoming',

            age: clientDetails.age ? parseInt(clientDetails.age) : undefined,
            days: clientDetails.days ? parseInt(clientDetails.days) : undefined,
            mobile: clientDetails.contact,
            origin: clientDetails.origin,
            from: clientDetails.origin || travelDetails.departure.airport,
            to: clientDetails.destination || travelDetails.returnTrip.airport,
            totalDays: clientDetails.days ? parseInt(clientDetails.days) : undefined,

            // New Relations
            flights: flights,
            hotelStays: stays,

            // Keep JSON for backward compatibility / reference if needed, but preferably remove. 
            // We'll set them to undefined or derived for legacy support if the API still expects them.
            // The API now handles 'flights' and 'hotelStays', so we don't need 'travelDetails' or 'hotelDetails' here.

            itineraryDays: days.map((day, index) => ({
                dayNumber: index + 1,
                activities: day.activities.map(act => ({
                    time: act.time,
                    duration: act.duration,
                    title: act.title,
                    location: act.location,
                    notes: act.notes,
                    status: act.status || 'upcoming',
                    lat: act.lat,
                    lng: act.lng
                }))
            }))
        };

        try {
            if (isEditing && initialData) {
                await updateItinerary(initialData.id, newItinerary);
            } else {
                await addItinerary(newItinerary);
            }
            router.push('/dashboard');
        } catch (error) {
            console.error("Failed to save itinerary", error);
            alert("Failed to save itinerary");
        }
    };



    if (isCompleted) {
        // Read-only view logic could be handled here or by disabling inputs
        // For now, let's disable the save buttons
    }

    return (
        <div className="max-w-5xl mx-auto pb-20 animate-in fade-in duration-500 space-y-8">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold text-gray-900">{isEditing ? 'Edit Itinerary' : 'Create New Itinerary'}</h1>
                <div className="flex gap-4">
                    {/* Draft: Save Draft + Finalize. Upcoming: Update only. Active/Completed: handled below. */}
                    {!isActive && !isUpcoming && !isCompleted && (
                        <Button variant="outline" onClick={() => handleSave('Draft')}>
                            <Save className="w-4 h-4 mr-2" />
                            Save Draft
                        </Button>
                    )}
                    {isUpcoming ? (
                        <Button className="bg-primary-600 hover:bg-primary-700 text-white" onClick={() => handleSave('Active')}>
                            <Save className="w-4 h-4 mr-2" />
                            Update Itinerary
                        </Button>
                    ) : !isCompleted ? (
                        <Button className="bg-primary-600 hover:bg-primary-700 text-white" onClick={() => handleSave('Active')}>
                            <Send className="w-4 h-4 mr-2" />
                            {isEditing && isActive ? 'Update Itinerary' : 'Finalize Itinerary'}
                        </Button>
                    ) : (
                        <Button variant="secondary" disabled>
                            Itinerary Completed
                        </Button>
                    )}
                </div>
            </div>

            <ClientDetailsForm
                formData={clientDetails}
                onChange={handleClientChange}
                readOnly={isActive || isCompleted}
            />

            <TravelDetails
                departure={travelDetails.departure}
                returnTrip={travelDetails.returnTrip}
                onChange={handleTravelChange}
                disabledDeparture={isDeparturePassed}
                disabledReturn={isReturnPassed}
            />

            <HotelStays stays={stays} onChange={setStays} />

            <DayBuilder
                days={days}
                onChange={(newDays) => {
                    setDays(newDays);
                    setClientDetails(prev => ({
                        ...prev,
                        days: newDays.length.toString()
                    }));
                }}
                startDate={travelDetails.departure.date}
                stays={stays}
                isActive={isActive}
                isCompleted={isCompleted}
            />
        </div>
    );
}
