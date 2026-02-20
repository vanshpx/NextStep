
async function checkAPI() {
    const id = 9;
    console.log(`Checking API for Itinerary ${id}...`);
    try {
        const res = await fetch(`http://localhost:3000/api/itineraries/${id}`);
        if (!res.ok) throw new Error(res.statusText);

        const data = await res.json();
        const acts = data.itineraryDays.flatMap(d => d.activities);

        const targets = acts.filter(a => a.title.toLowerCase().includes('juhu') || a.title.toLowerCase().includes('marine'));

        console.log(`Found ${targets.length} targets.`);

        if (targets.length > 0) {
            console.log(JSON.stringify(targets[0], null, 2));
        } else {
            console.log("No Juhu/Marine found.");
        }
    } catch (err) {
        console.error(err);
    }
}
checkAPI();
