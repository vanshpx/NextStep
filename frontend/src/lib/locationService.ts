import { LocationData } from "@/components/ui/AutocompleteInput";

// OpenStreetMap Nominatim API
const NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search";

export async function searchLocations(query: string): Promise<LocationData[]> {
    if (!query || query.length < 2) return [];

    try {
        const url = `${NOMINATIM_BASE_URL}?format=json&q=${encodeURIComponent(query)}&limit=5&addressdetails=1`;

        const response = await fetch(url, {
            headers: {
                'Accept-Language': 'en-US,en;q=0.5',
                // Proper etiquette for OSM Nominatim usage
                'User-Agent': 'ItineraryBuilderApp/1.0'
            }
        });

        if (!response.ok) {
            throw new Error(`Location search failed: ${response.statusText}`);
        }

        const data = await response.json();

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        return data.map((item: any) => {
            // Construct a readable label
            // Prefer: Name, City, Country or just Display Name
            const name = item.name || item.display_name.split(',')[0];
            const address = item.address || {};
            const city = address.city || address.town || address.village || address.hamlet || address.state || '';
            const country = address.country || '';

            let label = item.display_name;
            if (name && city && country) {
                // Cleaner format if possible
                label = `${name}, ${city}, ${country}`;
            }

            return {
                label: label,
                lat: parseFloat(item.lat),
                lng: parseFloat(item.lon)
            };
        });

    } catch (error) {
        console.error("Error searching locations:", error);
        return [];
    }
}
