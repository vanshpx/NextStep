
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
    const activities = await prisma.activity.findMany(); // Fetch all, filter in JS

    console.log(`Scanning ${activities.length} activities...`);

    for (const act of activities) {
        let lat, lng;
        const title = (act.title || "").toLowerCase();
        const location = (act.location || "").toLowerCase();

        if (title.includes('juhu') || location.includes('juhu')) {
            lat = 19.0988;
            lng = 72.8264;
        } else if (title.includes('marine') || location.includes('marine')) {
            lat = 18.9440;
            lng = 72.8230;
        }

        if (lat && lng) {
            console.log(`Updating Activity ${act.id} (${act.title}) -> Lat: ${lat}, Lng: ${lng}`);
            await prisma.activity.update({
                where: { id: act.id },
                data: { lat, lng }
            });
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
