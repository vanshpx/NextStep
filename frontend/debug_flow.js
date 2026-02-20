
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function checkDB() {
    console.log("--- 1. DATABASE CHECK ---");
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

    if (activities.length === 0) {
        console.log("❌ No matching activities found in DB.");
    } else {
        activities.forEach(a => {
            console.log(`Activity [${a.id}] "${a.title}"`);
            console.log(`   -> Lat: ${a.lat}, Lng: ${a.lng}`);
            if (a.lat && a.lng) console.log("   ✅ Valid Coordinates");
            else console.log("   ❌ MISSING Coordinates");
        });
    }
}

async function checkAPI() {
    console.log("\n--- 2. API RESPONSE CHECK ---");
    // We need to know the Itinerary ID. Let's assume the latest one or ID 9 as seen in previous logs.
    const latest = await prisma.itinerary.findFirst({ orderBy: { updatedAt: 'desc' } });
    if (!latest) {
        console.log("❌ No itineraries found to text API.");
        return;
    }
    const id = latest.id;
    console.log(`Fetching API for Itinerary ID: ${id}...`);

    try {
        const res = await fetch(`http://localhost:3000/api/itineraries/${id}`);
        if (!res.ok) {
            console.log(`❌ API Error: ${res.status} ${res.statusText}`);
            const text = await res.text();
            console.log(text);
            return;
        }

        const data = await res.json();
        const apiActivities = data.itineraryDays.flatMap(d => d.activities);

        console.log(`API returned ${apiActivities.length} total activities.`);

        // Filter for our targets
        const targets = apiActivities.filter(a =>
            (a.title && a.title.toLowerCase().includes('juhu')) ||
            (a.location && a.location.toLowerCase().includes('juhu')) ||
            (a.title && a.title.toLowerCase().includes('marine')) ||
            (a.location && a.location.toLowerCase().includes('marine'))
        );

        if (targets.length === 0) {
            console.log("⚠️ API did not return Juhu/Marine activities (maybe they belong to a different itinerary?)");
        } else {
            targets.forEach(a => {
                console.log(`API Activity [${a.id}] "${a.title}"`);
                console.log(`   -> Lat: ${a.lat}, Lng: ${a.lng}`);
                if (a.lat && a.lng) console.log("   ✅ API Returns Coordinates");
                else console.log("   ❌ API MISSING Coordinates");
            });
        }

    } catch (err) {
        console.error("❌ Failed to fetch API:", err.message);
    }
}

async function main() {
    await checkDB();
    await checkAPI();
}

main()
    .catch(e => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
