
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    const activities = await prisma.activity.findMany();

    const targets = activities.filter(a =>
        (a.title && a.title.toLowerCase().includes('juhu')) ||
        (a.location && a.location.toLowerCase().includes('juhu')) ||
        (a.title && a.title.toLowerCase().includes('marine')) ||
        (a.location && a.location.toLowerCase().includes('marine'))
    );

    console.log(`Found ${targets.length} targets to force update.`);

    for (const a of targets) {
        let lat = 0, lng = 0;
        if ((a.title && a.title.toLowerCase().includes('juhu')) || (a.location && a.location.toLowerCase().includes('juhu'))) {
            lat = 19.0988;
            lng = 72.8264;
        } else {
            lat = 18.9440;
            lng = 72.8230;
        }

        console.log(`Force Updating [${a.id}] "${a.title}" -> ${lat}, ${lng}`);
        await prisma.activity.update({
            where: { id: a.id },
            data: { lat, lng }
        });
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
