import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function cleanPriyaItinerary() {
    try {
        // Find Priya Sharma's itinerary
        const priya = await prisma.itinerary.findFirst({
            where: {
                client: {
                    contains: 'Priya Sharma'
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

        if (!priya) {
            console.log('Priya Sharma itinerary not found');
            return;
        }

        console.log('Found Priya Sharma itinerary:', priya.client);
        console.log('Current status:', priya.status);

        // Clear all 'issue' statuses from activities
        for (const day of priya.itineraryDays) {
            for (const activity of day.activities) {
                if (activity.status === 'issue') {
                    console.log(`Clearing issue status from: ${activity.title}`);
                    await prisma.activity.update({
                        where: { id: activity.id },
                        data: {
                            status: 'upcoming',
                            notes: null // Clear the disruption notes
                        }
                    });
                }
            }
        }

        // Update itinerary status to Active
        await prisma.itinerary.update({
            where: { id: priya.id },
            data: {
                status: 'Active',
                issueSummary: null
            }
        });

        console.log('✅ Cleaned Priya Sharma itinerary - all activities back to normal');

    } catch (error) {
        console.error('Error cleaning Priya itinerary:', error);
    } finally {
        await prisma.$disconnect();
    }
}

cleanPriyaItinerary();
