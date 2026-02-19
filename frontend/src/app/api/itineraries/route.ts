import { NextResponse } from 'next/server';
import prisma from '@/lib/prisma';
import { Prisma } from '@prisma/client';

export async function GET() {
    try {
        const itineraries = await prisma.itinerary.findMany({
            include: {
                flights: true,
                hotelStays: true,
                itineraryDays: {
                    include: {
                        activities: true,
                    },
                },
            },
            orderBy: {
                updatedAt: 'desc',
            },
        });

        const mappedItineraries = itineraries.map((it: any) => ({
            id: it.id,
            c: it.client,
            d: it.destination,
            s: it.status,
            status: it.status,
            date: it.dateRange,
            flights: it.flights,
            hotelStays: it.hotelStays,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            itineraryDays: it.itineraryDays.map((d: any) => ({
                dayNumber: d.dayNumber,
                activities: d.activities,
            })),
        }));

        return NextResponse.json(mappedItineraries);
    } catch (error) {
        console.error('Error fetching itineraries:', error);
        return NextResponse.json({ error: 'Failed to fetch itineraries' }, { status: 500 });
    }
}

export async function POST(request: Request) {
    try {
        const body = await request.json();

        // Frontend sends: c, d, s, date, flights, hotelStays, itineraryDays
        // We need to map to: client, destination, status, dateRange

        const {
            c, d, s, date,
            flights, hotelStays, itineraryDays,
            age, days, email, mobile, origin, from, to, totalDays,
            displayPrice // eslint-disable-line @typescript-eslint/no-unused-vars
        } = body;

        const newItinerary = await prisma.itinerary.create({
            data: {
                client: c,
                destination: d,
                dateRange: date || 'Upcoming',
                status: s || 'Draft',

                // Detailed fields
                age, days, email, mobile, origin, from, to, totalDays,

                flights: {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    create: flights?.map((f: any) => ({
                        type: f.type,
                        date: f.date,
                        airline: f.airline,
                        flightNumber: f.flightNumber,
                        flightTime: f.flightTime, // map
                        arrivalTime: f.arrivalTime,
                        airport: f.airport,
                        lat: f.lat,
                        lng: f.lng
                    })) || []
                },

                hotelStays: {
                    create: hotelStays?.map((h: Prisma.HotelStayCreateWithoutItineraryInput) => ({
                        hotelName: h.hotelName,
                        checkIn: h.checkIn,
                        checkOut: h.checkOut,
                        notes: h.notes,
                        lat: h.lat,
                        lng: h.lng
                    })) || []
                },

                itineraryDays: {
                    create: itineraryDays?.map((day: any, index: number) => ({
                        dayNumber: day.dayNumber || index + 1,
                        activities: {
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            create: day.activities?.map((act: any) => ({
                                time: act.time,
                                duration: act.duration,
                                title: act.title,
                                location: act.location,
                                notes: act.notes,
                                status: act.status || 'upcoming',
                                lat: act.lat,
                                lng: act.lng,
                            })) || [],
                        },
                    })) || [],
                },
            },
            include: {
                flights: true,
                hotelStays: true,
                itineraryDays: {
                    include: {
                        activities: true,
                    },
                },
            },
        });

        return NextResponse.json({
            ...newItinerary,
            c: newItinerary.client,
            d: newItinerary.destination,
            s: newItinerary.status,
            date: newItinerary.dateRange,
        });
    } catch (error) {
        console.error('Error creating itinerary:', error);
        return NextResponse.json({ error: 'Failed to create itinerary' }, { status: 500 });
    }
}
