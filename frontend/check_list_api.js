
async function checkListAPI() {
    console.log("Checking LIST API (GET /api/itineraries)...");
    try {
        const res = await fetch(`http://localhost:3000/api/itineraries`);
        if (!res.ok) throw new Error(res.statusText);

        const data = await res.json();
        console.log(`Fetched ${data.length} itineraries.`);

        const targetItinerary = data.find(i => i.id === 9);
        if (!targetItinerary) {
            console.log("Itinerary 9 not found in list.");
            return;
        }

        console.log("Inspecting Itinerary 9 from List:");
        if (!targetItinerary.itineraryDays) {
            console.log("❌ itineraryDays is MISSING!");
        } else {
            const acts = targetItinerary.itineraryDays.flatMap(d => d.activities);
            const targetAct = acts.find(a => a.title.toLowerCase().includes('marine') || a.title.toLowerCase().includes('juhu'));
            if (targetAct) {
                console.log("Found Marine/Juhu Activity in LIST response:");
                console.log(JSON.stringify(targetAct, null, 2));
            } else {
                console.log("❌ Marine/Juhu Activity NOT FOUND in List response (but might be in DB).");
            }
        }
    } catch (err) {
        console.error(err);
    }
}
checkListAPI();
