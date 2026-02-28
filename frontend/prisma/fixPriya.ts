import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function fixPriyaItinerary() {
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

        // Check if any activity has status 'issue'
        let hasDisruption = false;
        let disruptionType = '';

        for (const day of priya.itineraryDays) {
            for (const activity of day.activities) {
                if (activity.status === 'issue') {
                    hasDisruption = true;
                    disruptionType = activity.notes || 'Disrupted';
                    console.log(`Found disrupted activity: ${activity.title} - ${activity.notes}`);
                }
            }
        }

        if (hasDisruption) {
            // Update itinerary status to Disrupted
            await prisma.itinerary.update({
                where: { id: priya.id },
                data: {
                    status: 'Disrupted',
                    issueSummary: disruptionType
                }
            });

            console.log('✅ Updated Priya Sharma itinerary status to Disrupted');
            console.log('Issue summary:', disruptionType);
        } else {
            console.log('No disrupted activities found');
        }

    } catch (error) {
        console.error('Error fixing Priya itinerary:', error);
    } finally {
        await prisma.$disconnect();
    }
}

fixPriyaItinerary();
