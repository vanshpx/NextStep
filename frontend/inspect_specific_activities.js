
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    const activities = await prisma.activity.findMany({
        where: {
            OR: [
                { title: { contains: 'Juhu', mode: 'insensitive' } },
                { location: { contains: 'Juhu', mode: 'insensitive' } },
                { title: { contains: 'Marine', mode: 'insensitive' } },
                { location: { contains: 'Marine', mode: 'insensitive' } }
            ]
        }
    });

    console.log(`Found ${activities.length} activities.`);

    activities.forEach(a => {
        console.log(`[${a.id}] ${a.title} @ ${a.location}`);
        console.log(`    Lat: ${a.lat}, Lng: ${a.lng}`);
    });
}

main()
    .catch(e => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
