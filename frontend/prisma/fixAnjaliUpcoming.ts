import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    await prisma.itinerary.updateMany({
        where: { client: { contains: 'Anjali Mehta' } },
        data: { status: 'Upcoming' }
    });
    console.log('Updated Anjali Mehta trip to Upcoming');
}

main()
    .catch(console.error)
    .finally(async () => {
        await prisma.$disconnect();
    });
