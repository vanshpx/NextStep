import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    // 1. Find the itinerary for Anjali Mehta
    const itinerary = await prisma.itinerary.findFirst({
        where: { client: { contains: 'Anjali Mehta' } },
        include: { itineraryDays: { include: { activities: true } } }
    });

    if (!itinerary) {
        console.error('Anjali Mehta itinerary not found');
        return;
    }

    console.log(`Found itinerary ID: ${itinerary.id}, current status: ${itinerary.status}`);

    // 2. Update status to 'Active'
    await prisma.itinerary.update({
        where: { id: itinerary.id },
        data: { status: 'Active' }
    });

    // 3. Mark activities as completed SEQUENTIALLY up to a random point
    const allActivities = itinerary.itineraryDays
        .sort((a, b) => a.dayNumber - b.dayNumber)
        .flatMap(d => d.activities);

    if (allActivities.length > 0) {
        // Reset all to upcoming
        for (const act of allActivities) {
            await prisma.activity.update({
                where: { id: act.id },
                data: { status: 'upcoming' }
            });
        }

        const randomIdx = Math.floor(Math.random() * (allActivities.length - 1)) + 1; // At least 1 completed

        for (let i = 0; i <= randomIdx; i++) {
            await prisma.activity.update({
                where: { id: allActivities[i].id },
                data: { status: 'completed' }
            });
        }

        console.log(`Updated first ${randomIdx + 1} activities to status: completed`);
    }

    console.log('Successfully updated Anjali Mehta trip to Active.');
}

main()
    .catch((e) => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
