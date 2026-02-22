"use client";

import ItineraryTable from "@/components/dashboard/ItineraryTable";
import { useItinerary } from "@/context/ItineraryContext";

export default function AllTripsPage() {
    useItinerary();

    return (
        <div className="space-y-6">
            <ItineraryTable title="All Trips" showViewAll={false} />
        </div>
    );
}
