import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    console.log("Testing Prisma types...");
    try {
        // Find an existing itinerary to update
        const itinerary = await prisma.itinerary.findFirst();
        if (!itinerary) {
            console.log("No itinerary found to test with.");
            return;
        }

        console.log(`Updating itinerary ID ${itinerary.id} with numbers in string fields...`);

        await prisma.itinerary.update({
            where: { id: itinerary.id },
            data: {
                // @ts-ignore - simulating dynamic body data
                age: 25,
                // @ts-ignore
                days: 5
            }
        });

        console.log("Update successful! Prisma auto-coerced numbers to strings.");
    } catch (error) {
        console.error("Update failed:", error);
    } finally {
        await prisma.$disconnect();
    }
}

main();
