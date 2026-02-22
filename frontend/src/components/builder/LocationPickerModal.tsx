"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Check, MapPin, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import AutocompleteInput from "@/components/ui/AutocompleteInput";
import { GoogleMap, Marker } from "@react-google-maps/api";
import { useGoogleMaps } from "@/lib/googleMaps";

interface LocationPickerModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (lat: number, lng: number) => void;
    initialLat?: number;
    initialLng?: number;
}

const mapContainerStyle = {
    width: '100%',
    height: '100%'
};

const defaultCenter = {
    lat: 20.5937,
    lng: 78.9629
};

export default function LocationPickerModal({ isOpen, onClose, onSelect, initialLat, initialLng }: LocationPickerModalProps) {
    const { isLoaded, loadError } = useGoogleMaps();
    const [marker, setMarker] = useState<{ lat: number; lng: number } | null>(null);
    const [map, setMap] = useState<google.maps.Map | null>(null);
    const [searchValue, setSearchValue] = useState("");

    useEffect(() => {
        if (isOpen) {
            setSearchValue("");
            if (initialLat && initialLng) {
                setMarker({ lat: initialLat, lng: initialLng });
            } else {
                setMarker(null);
            }
        }
    }, [isOpen, initialLat, initialLng]);

    const handleMapClick = useCallback((e: google.maps.MapMouseEvent) => {
        if (e.latLng) {
            setMarker({
                lat: e.latLng.lat(),
                lng: e.latLng.lng()
            });
        }
    }, []);

    const onMapLoad = useCallback((map: google.maps.Map) => {
        setMap(map);
    }, []);

    // Effect to pan map when marker updates via search
    useEffect(() => {
        if (marker && map && isOpen) {
            map.panTo(marker);
            map.setZoom(16);
        }
    }, [marker, map, isOpen]);

    const handleConfirm = () => {
        if (marker) {
            onSelect(marker.lat, marker.lng);
            onClose();
        }
    };

    if (!isOpen) return null;

    if (loadError) return <div>Error loading maps</div>;
    if (!isLoaded) return <div>Loading Maps...</div>;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="flex justify-between items-center p-4 border-b border-gray-100">
                    <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                        <MapPin className="w-5 h-5 text-primary-600" />
                        Select Location
                    </h2>
                    <Button variant="ghost" size="icon" onClick={onClose}>
                        <X className="w-5 h-5 text-gray-500" />
                    </Button>
                </div>

                {/* Search */}
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 z-10">
                    <div className="max-w-md mx-auto">
                        <AutocompleteInput
                            placeholder="Search map location..."
                            value={searchValue}
                            onChange={(val, loc) => {
                                setSearchValue(val);
                                if (loc) {
                                    setMarker({ lat: loc.lat, lng: loc.lng });
                                }
                            }}
                            icon={<Search className="w-4 h-4 text-gray-400" />}
                        />
                    </div>
                </div>

                {/* Map */}
                <div className="flex-1 relative bg-gray-100">
                    <GoogleMap
                        mapContainerStyle={mapContainerStyle}
                        center={marker || defaultCenter}
                        zoom={marker ? 16 : 5}
                        onClick={handleMapClick}
                        onLoad={onMapLoad}
                        options={{
                            streetViewControl: false,
                            mapTypeControl: false,
                            fullscreenControl: false
                        }}
                    >
                        {marker && <Marker position={marker} />}
                    </GoogleMap>

                    {!marker && (
                        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-white/90 backdrop-blur px-4 py-2 rounded-full shadow-lg text-sm font-medium text-gray-700 z-[400] pointer-events-none">
                            Click on map or search above
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-gray-100 flex justify-end gap-3 bg-gray-50">
                    <Button variant="outline" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleConfirm}
                        disabled={!marker}
                        className="bg-primary-600 hover:bg-primary-700 text-white"
                    >
                        <Check className="w-4 h-4 mr-2" />
                        Set Location
                    </Button>
                </div>
            </div>
        </div>
    );
}
