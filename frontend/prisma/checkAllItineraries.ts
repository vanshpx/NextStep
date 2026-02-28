import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    const itineraries = await prisma.itinerary.findMany({
        include: {
            flights: true,
            itineraryDays: {
                include: {
                    activities: true
                }
            }
        }
    });

    console.log('All Itineraries:\n');
    
    const now = new Date();
    
    itineraries.forEach(it => {
        console.log(`\n${it.client} (ID: ${it.id})`);
        console.log(`  Status: ${it.status}`);
        console.log(`  Date Range: ${it.dateRange}`);
        
        const returnFlight = it.flights.find(f => f.type === 'Return');
        if (returnFlight?.date) {
            const returnDate = new Date(returnFlight.date);
            console.log(`  Return Flight: ${returnDate.toDateString()}`);
            console.log(`  Should be completed: ${now > returnDate ? 'YES' : 'NO'}`);
        }
        
        if (it.itineraryDays.length > 0) {
            console.log(`  Days: ${it.itineraryDays.length}`);
            const lastDay = it.itineraryDays[it.itineraryDays.length - 1];
            console.log(`  Last day activities: ${lastDay.activities.length}`);
        }
    });
}

main()
    .catch(console.error)
    .finally(() => prisma.$disconnect());
