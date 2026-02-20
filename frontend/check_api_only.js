
async function checkAPI() {
    console.log("--- API RESPONSE CHECK ---");
    // Hardcoding ID 9 as seen in previous logs
    const id = 9;
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
            // Log a few sample activities to see what's there
            console.log("Sample activities:", apiActivities.slice(0, 3).map(a => `${a.title} (${a.lat}, ${a.lng})`));
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

checkAPI();
