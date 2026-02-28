import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    // Update Anjali's itinerary to Completed
    await prisma.itinerary.update({
        where: { id: 45 },
        data: {
            status: 'Completed',
            issueSummary: null
        }
    });
    
    console.log('Updated Anjali Mehta itinerary to Completed');
}

main()
    .catch(console.error)
    .finally(() => prisma.$disconnect());
