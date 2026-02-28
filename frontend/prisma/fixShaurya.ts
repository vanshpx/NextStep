import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    // Find Shaurya's itinerary
    const itinerary = await prisma.itinerary.findFirst({
        where: {
            client: {
                contains: 'Shaurya'
            }
        },
        include: {
            itineraryDays: {
                include: {
                    activities: true
                }
            }
        }
    });

    if (!itinerary) {
        console.log('Shaurya itinerary not found');
        return;
    }

    console.log('Fixing Shaurya itinerary...');

    // Clear issueSummary
    await prisma.itinerary.update({
        where: { id: itinerary.id },
        data: {
            issueSummary: null
        }
    });

    // Fix all activities with 'issue' status
    for (const day of itinerary.itineraryDays) {
        for (const activity of day.activities) {
            if (activity.status === 'issue') {
                await prisma.activity.update({
                    where: { id: activity.id },
                    data: {
                        status: 'upcoming',
                        notes: ''
                    }
                });
                console.log(`Fixed activity: ${activity.title}`);
            }
        }
    }

    console.log('Done!');
}

main()
    .catch(console.error)
    .finally(() => prisma.$disconnect());
