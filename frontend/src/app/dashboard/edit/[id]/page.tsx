"use client";

import { useEffect, useState, useMemo } from "react";
import ItineraryBuilderForm from "@/components/builder/ItineraryBuilderForm";
import { useItinerary } from "@/context/ItineraryContext";

export default function EditItineraryPage({ params }: { params: Promise<{ id: string }> }) {
    const { getItinerary } = useItinerary();

    const [id, setId] = useState<string | null>(null);

    // Unwrap params
    useEffect(() => {
        params.then(p => setId(p.id));
    }, [params]);

    const itinerary = useMemo(() => {
        if (id) {
            return getItinerary(parseInt(id));
        }
        return null;
    }, [id, getItinerary]);

    if (!itinerary) {
        return <div className="p-8 text-center">Loading itinerary...</div>;
    }

    return <ItineraryBuilderForm initialData={itinerary} isEditing={true} />;
}
