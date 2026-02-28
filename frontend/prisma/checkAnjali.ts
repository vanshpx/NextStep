import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    const itinerary = await prisma.itinerary.findFirst({
        where: { client: { contains: 'Anjali Mehta' } },
        include: { itineraryDays: { include: { activities: true } } }
    });

    if (!itinerary) {
        console.error('Anjali Mehta itinerary not found');
        return;
    }

    console.log('--- ITINERARY ---');
    console.log(`ID: ${itinerary.id}, Status: ${itinerary.status}`);

    itinerary.itineraryDays.sort((a, b) => a.dayNumber - b.dayNumber).forEach(day => {
        console.log(`Day ${day.dayNumber}:`);
        day.activities.forEach(act => {
            console.log(`  [${act.status}] ${act.time} - ${act.title}`);
        });
    });
}

main().finally(() => prisma.$disconnect());
