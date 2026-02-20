
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    const activities = await prisma.activity.findMany(); // Fetch all

    const targets = activities.filter(a =>
        (a.title && a.title.toLowerCase().includes('juhu')) ||
        (a.location && a.location.toLowerCase().includes('juhu')) ||
        (a.title && a.title.toLowerCase().includes('marine')) ||
        (a.location && a.location.toLowerCase().includes('marine'))
    );

    console.log(`Found ${targets.length} matching activities out of ${activities.length} total.`);

    targets.forEach(a => {
        console.log(`[ID: ${a.id}] "${a.title}" @ "${a.location}"`);
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
