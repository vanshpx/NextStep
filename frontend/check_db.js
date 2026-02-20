
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    const latest = await prisma.itinerary.findFirst({
        orderBy: { updatedAt: 'desc' },
        include: {
            itineraryDays: {
                include: { activities: true }
            },
            flights: true
        }
    });

    if (!latest) {
        console.log('No itineraries found.');
        return;
    }

    console.log(`Latest Itinerary ID: ${latest.id}`);
    console.log(`Client: ${latest.client}`);

    console.log('--- Flights ---');
    latest.flights.forEach(f => {
        console.log(`Flight ${f.type}: ${f.airport} (Lat: ${f.lat}, Lng: ${f.lng})`);
    });

    console.log('--- Activities ---');
    latest.itineraryDays.forEach(day => {
        console.log(`Day ${day.dayNumber}:`);
        day.activities.forEach(act => {
            console.log(`  Activity: ${act.title} @ ${act.location}`);
            console.log(`  Coords: Lat=${act.lat}, Lng=${act.lng}`);
        });
    });
}

main()
    .catch(e => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
