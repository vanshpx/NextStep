"use client";

import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, Polyline } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Fix for default marker icon in Next.js
const iconUrl = "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png";
const iconRetinaUrl = "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png";
const shadowUrl = "https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png";

const defaultIcon = L.icon({
    iconUrl,
    iconRetinaUrl,
    shadowUrl,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41],
} as L.IconOptions);

// Component to handle map view updates
function MapController({ selectedActivity, activities }: { selectedActivity: Activity | null; activities: Activity[] }) {
    const map = useMap();

    useEffect(() => {
        if (selectedActivity && selectedActivity.lat && selectedActivity.lng) {
            map.flyTo([selectedActivity.lat, selectedActivity.lng], 16, {
                duration: 1.5,
                easeLinearity: 0.25
            });
        } else if (activities.length > 0) {
            // Fit bounds to all activities if no specific selection
            const bounds = L.latLngBounds(activities.map(a => [a.lat!, a.lng!]));
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    }, [selectedActivity, activities, map]);

    return null;
}

interface Activity {
    id: number;
    title: string;
    time: string;
    location: string;
    lat?: number;
    lng?: number;
}

interface ClientMapProps {
    activities: Activity[];
    selectedActivity: Activity | null;
}

export default function ClientMap({ activities = [], selectedActivity }: ClientMapProps) {
    // Default center (Ahmedabad)
    const defaultCenter: [number, number] = [23.0225, 72.5714];

    // Filter activities that have coordinates
    const validActivities = activities.filter(a => a.lat && a.lng);
    const polylinePositions = validActivities.map(a => [a.lat!, a.lng!] as [number, number]);

    // Cast components to any to avoid TypeScript errors with React 19 / React-Leaflet v5
    /* eslint-disable @typescript-eslint/no-explicit-any */
    const MapContainerAny = MapContainer as any;
    const TileLayerAny = TileLayer as any;
    const MarkerAny = Marker as any;
    const PolylineAny = Polyline as any;
    const PopupAny = Popup as any;
    /* eslint-enable @typescript-eslint/no-explicit-any */

    return (
        <MapContainerAny
            center={defaultCenter}
            zoom={11}
            minZoom={3}
            maxBounds={[[-90, -180], [90, 180]]}
            maxBoundsViscosity={1.0}
            style={{ height: "100%", width: "100%", zIndex: 0 }}
            scrollWheelZoom={true}
        >
            <TileLayerAny
                attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
                url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
            />

            <MapController selectedActivity={selectedActivity} activities={validActivities} />

            {validActivities.map((activity) => (
                <MarkerAny
                    key={activity.id}
                    position={[activity.lat!, activity.lng!]}
                    icon={defaultIcon}
                >
                    <PopupAny>
                        <div className="p-1">
                            <h3 className="font-bold text-sm">{activity.title}</h3>
                            <p className="text-xs text-gray-500">{activity.time}</p>
                            <p className="text-xs mt-1">{activity.location}</p>
                        </div>
                    </PopupAny>
                </MarkerAny>
            ))}

            {polylinePositions.length > 1 && (
                <PolylineAny
                    positions={polylinePositions}
                    color="#2563EB"
                    weight={3}
                    opacity={0.6}
                    dashArray="10, 10"
                />
            )}
        </MapContainerAny>
    );
}
