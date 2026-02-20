
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

    console.log(`Found ${activities.length} matching activities.`);

    for (const act of activities) {
        let lat, lng;
        if (act.title.toLowerCase().includes('juhu') || act.location.toLowerCase().includes('juhu')) {
            lat = 19.0988;
            lng = 72.8264;
        } else if (act.title.toLowerCase().includes('marine') || act.location.toLowerCase().includes('marine')) {
            lat = 18.9440;
            lng = 72.8230;
        }

        if (lat && lng) {
            await prisma.activity.update({
                where: { id: act.id },
                data: { lat, lng }
            });
            console.log(`Updated Activity ${act.id} (${act.title}) with Lat: ${lat}, Lng: ${lng}`);
        }
    }
}

main()
    .catch(e => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
