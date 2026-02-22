import { NextResponse } from 'next/server';
import prisma from '@/lib/prisma';
import { Prisma } from '@prisma/client';
import { computeActivityOrder } from '@/lib/sortActivities';

export const dynamic = 'force-dynamic';

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
                        activities: {
                            orderBy: { order: 'asc' },
                        },
                    },
                },
            },
        });

        if (!itinerary) {
            return NextResponse.json({ error: 'Itinerary not found' }, { status: 404 });
        }

        // Map to frontend interface
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const it = itinerary as any;
        const mappedItinerary = {
            id: it.id,
            c: it.client,
            d: it.destination,
            s: it.status,
            status: it.status,
            date: it.dateRange,
            flights: it.flights,
            hotelStays: it.hotelStays,
            age: it.age,
            days: it.days,
            email: it.email,
            mobile: it.mobile,
            origin: it.origin,
            from: it.from,
            to: it.to,
            totalDays: it.totalDays,
            agentName: it.agentName,
            agentPhone: it.agentPhone,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            itineraryDays: it.itineraryDays.map((day: any) => ({
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
        // The form sends short keys (c, d, s, date) — accept both naming conventions
        const {
            itineraryDays, flights, hotelStays,
            // Short keys (sent by itinerary builder form)
            c, d, s, date,
            // Long keys (direct API usage / disruption updates / etc.)
            client: clientLong, destination: destinationLong, dateRange, status: statusLong,
            // Detail fields
            progress, age, days, email, mobile, origin, from, to, totalDays, agentName, agentPhone,
        } = body;

        // Resolve with short keys taking priority over long keys
        const resolvedClient = c ?? clientLong;
        const resolvedDestination = d ?? destinationLong;
        const resolvedStatus = s ?? statusLong;
        const resolvedDateRange = date ?? dateRange;

        // Use transaction to ensure consistency
        const updatedItinerary = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
            // 1. Update main itinerary fields
            await tx.itinerary.update({
                where: { id: parseInt(id) },
                data: {
                    client: resolvedClient,
                    destination: resolvedDestination,
                    dateRange: resolvedDateRange,
                    status: resolvedStatus,
                    progress,
                    age: age?.toString(),
                    days: days?.toString(),
                    email,
                    mobile,
                    origin,
                    from,
                    to,
                    totalDays,
                    agentName,
                    agentPhone
                },
            });

            // 2. Handle Flights (Delete All -> Create New)
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

            // 4. Replace itinerary days with atomically ordered activities
            if (itineraryDays && Array.isArray(itineraryDays)) {
                // Delete all existing days (cascades to activities)
                await tx.day.deleteMany({
                    where: { itineraryId: parseInt(id) },
                });

                // Recreate each day, computing server-side chronological order
                for (const day of itineraryDays) {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const orderedActivities = computeActivityOrder(day.activities ?? []) as any[];

                    await tx.day.create({
                        data: {
                            dayNumber: day.dayNumber || day.day,
                            itineraryId: parseInt(id),
                            activities: {
                                create: orderedActivities.map(
                                    (act: Prisma.ActivityCreateWithoutDayInput & { order: number }) => ({
                                        time: act.time,
                                        duration: act.duration?.toString(),
                                        title: act.title,
                                        location: act.location,
                                        notes: act.notes,
                                        status: act.status || 'upcoming',
                                        lat: act.lat,
                                        lng: act.lng,
                                        order: act.order,
                                    } as any)
                                ),
                            },
                        },
                    });
                }
            }

            // 5. Fetch full updated itinerary — activities already in order due to
            // ORDER BY on the query and the order values we just wrote.
            return await tx.itinerary.findUnique({
                where: { id: parseInt(id) },
                include: {
                    flights: true,
                    hotelStays: true,
                    itineraryDays: {
                        include: {
                            activities: {
                                orderBy: { order: 'asc' },
                            },
                        },
                    },
                },
            });
        });

        if (!updatedItinerary) {
            return NextResponse.json({ error: 'Itinerary not found' }, { status: 404 });
        }

        // Map to frontend interface — must include ALL fields so the context
        // (which replaces its in-memory entry with this response) never loses
        // detail fields like origin/from/to after a save.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const ui = updatedItinerary as any;
        const mappedItinerary = {
            id: ui.id,
            c: ui.client,
            d: ui.destination,
            s: ui.status,
            status: ui.status,
            date: ui.dateRange,
            // Detail fields — must be present so builder form re-hydrates correctly
            age: ui.age,
            days: ui.days,
            email: ui.email,
            mobile: ui.mobile,
            origin: ui.origin,
            from: ui.from,
            to: ui.to,
            totalDays: ui.totalDays,
            agentName: ui.agentName,
            agentPhone: ui.agentPhone,
            flights: ui.flights,
            hotelStays: ui.hotelStays,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            itineraryDays: ui.itineraryDays.map((day: any) => ({
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
