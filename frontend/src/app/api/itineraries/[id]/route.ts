import { NextResponse } from 'next/server';
import prisma from '@/lib/prisma';
import { Prisma } from '@prisma/client';

export async function GET(
    request: Request,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;
        const itinerary = await prisma.itinerary.findUnique({
            where: {
                id: parseInt(id),
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

        if (!itinerary) {
            return NextResponse.json({ error: 'Itinerary not found' }, { status: 404 });
        }

        // Map to frontend interface
        const mappedItinerary = {
            id: itinerary.id,
            c: itinerary.client,
            d: itinerary.destination,
            s: itinerary.status,
            status: itinerary.status,
            date: itinerary.dateRange,
            flights: itinerary.flights,
            hotelStays: itinerary.hotelStays,
            age: itinerary.age,
            days: itinerary.days,
            email: itinerary.email,
            mobile: itinerary.mobile,
            origin: itinerary.origin,
            from: itinerary.from,
            to: itinerary.to,
            totalDays: itinerary.totalDays,
            itineraryDays: itinerary.itineraryDays.map((day) => ({
                id: day.id,
                dayNumber: day.dayNumber,
                activities: day.activities,
            })),
        };

        return NextResponse.json(mappedItinerary);
    } catch (error) {
        console.error('Error fetching itinerary:', error);
        return NextResponse.json({ error: 'Failed to fetch itinerary' }, { status: 500 });
    }
}

export async function DELETE(
    request: Request,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;
        await prisma.itinerary.delete({
            where: {
                id: parseInt(id),
            },
        });

        return NextResponse.json({ message: 'Itinerary deleted' });
    } catch (error) {
        console.error('Error deleting itinerary:', error);
        return NextResponse.json({ error: 'Failed to delete itinerary' }, { status: 500 });
    }
}

export async function PATCH(
    request: Request,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;
        const body = await request.json();

        // Separate relations from scalar fields
        const {
            itineraryDays, flights, hotelStays,
            client, destination, dateRange, status,
            progress, age, days, email, mobile, origin, from, to, totalDays,

        } = body;

        // Use transaction to ensure consistency
        const updatedItinerary = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
            // 1. Update main itinerary fields - use update with explicit data object
            await tx.itinerary.update({
                where: { id: parseInt(id) },
                data: {
                    client,
                    destination,
                    dateRange,
                    status,
                    progress,
                    age,
                    days,
                    email,
                    mobile,
                    origin,
                    from,
                    to,
                    totalDays
                },
            });

            // 2. Handle Flights (Delete All -> Create New is easiest for now)
            if (flights && Array.isArray(flights)) {
                await tx.flight.deleteMany({ where: { itineraryId: parseInt(id) } });
                if (flights.length > 0) {
                    await tx.flight.createMany({
                        data: flights.map((f: Prisma.FlightCreateManyInput) => ({
                            itineraryId: parseInt(id),
                            type: f.type,
                            date: f.date,
                            airline: f.airline,
                            flightNumber: f.flightNumber,
                            flightTime: f.flightTime,
                            arrivalTime: f.arrivalTime,
                            airport: f.airport,
                            lat: f.lat,
                            lng: f.lng
                        }))
                    });
                }
            }

            // 3. Handle Hotel Stays
            if (hotelStays && Array.isArray(hotelStays)) {
                await tx.hotelStay.deleteMany({ where: { itineraryId: parseInt(id) } });
                if (hotelStays.length > 0) {
                    await tx.hotelStay.createMany({
                        data: hotelStays.map((h: Prisma.HotelStayCreateManyInput) => ({
                            itineraryId: parseInt(id),
                            hotelName: h.hotelName,
                            checkIn: h.checkIn,
                            checkOut: h.checkOut,
                            notes: h.notes,
                            lat: h.lat,
                            lng: h.lng
                        }))
                    });
                }
            }

            // 4. If itineraryDays provided, replace them
            if (itineraryDays && Array.isArray(itineraryDays)) {
                await tx.day.deleteMany({
                    where: { itineraryId: parseInt(id) },
                });

                for (const day of itineraryDays) {
                    await tx.day.create({
                        data: {
                            dayNumber: day.dayNumber || day.day,
                            itineraryId: parseInt(id),
                            activities: {
                                create: day.activities.map((act: Prisma.ActivityCreateWithoutDayInput) => ({
                                    time: act.time,
                                    duration: act.duration,
                                    title: act.title,
                                    location: act.location,
                                    notes: act.notes,
                                    status: act.status || 'upcoming',
                                    lat: act.lat,
                                    lng: act.lng
                                })),
                            },
                        },
                    });
                }
            }

            // 5. Fetch full updated itinerary to return
            return await tx.itinerary.findUnique({
                where: { id: parseInt(id) },
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
        });

        if (!updatedItinerary) {
            return NextResponse.json({ error: 'Itinerary not found' }, { status: 404 });
        }

        // Map to frontend interface
        const mappedItinerary = {
            id: updatedItinerary.id,
            c: updatedItinerary.client,
            d: updatedItinerary.destination,
            s: updatedItinerary.status,
            status: updatedItinerary.status,
            date: updatedItinerary.dateRange,
            flights: updatedItinerary.flights,
            hotelStays: updatedItinerary.hotelStays,
            // ... other fields
            itineraryDays: updatedItinerary.itineraryDays.map((day) => ({
                id: day.id,
                dayNumber: day.dayNumber,
                activities: day.activities,
            })),
        };

        return NextResponse.json(mappedItinerary);
    } catch (error) {
        console.error('Error updating itinerary:', error);
        return NextResponse.json({ error: 'Failed to update itinerary' }, { status: 500 });
    }
}
