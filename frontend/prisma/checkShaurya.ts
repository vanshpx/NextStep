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

    if (itinerary) {
        console.log('Shaurya Itinerary:');
        console.log('ID:', itinerary.id);
        console.log('Status:', itinerary.status);
        console.log('IssueSummary:', itinerary.issueSummary);
        console.log('\nActivities:');
        
        itinerary.itineraryDays.forEach(day => {
            console.log(`\nDay ${day.dayNumber}:`);
            day.activities.forEach(act => {
                console.log(`  - ${act.title}`);
                console.log(`    Status: ${act.status}`);
                console.log(`    Notes: ${act.notes}`);
            });
        });
    } else {
        console.log('Shaurya itinerary not found');
    }
}

main()
    .catch(console.error)
    .finally(() => prisma.$disconnect());
