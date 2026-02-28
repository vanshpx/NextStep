"use client";

import { useState, useEffect, useRef } from "react";
import { MapPin, Search, Check, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { useGoogleMaps } from "@/lib/googleMaps";

export interface LocationData {
    label: string;
    lat: number;
    lng: number;
    placeId?: string; // Google Place ID
}

interface AutocompleteInputProps {
    label?: string;
    placeholder?: string;
    data?: LocationData[]; // Static list override
    value?: string;
    onChange: (value: string, location?: LocationData) => void;
    className?: string;
    icon?: React.ReactNode;
    disabled?: boolean;
    placeTypes?: string[];
}

export default function AutocompleteInput({
    label,
    placeholder = "Search...",
    data = [], // if provided, uses static filtering instead of Google
    value = "",
    onChange,
    className = "",
    icon,
    disabled = false,
    placeTypes = ['geocode', 'establishment']
}: AutocompleteInputProps) {
    const { isLoaded } = useGoogleMaps();
    const [query, setQuery] = useState(value);
    const [isOpen, setIsOpen] = useState(false);
    const [predictions, setPredictions] = useState<LocationData[]>([]);
    const [isValidSelection, setIsValidSelection] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const wrapperRef = useRef<HTMLDivElement>(null);
    const placesServiceRef = useRef<google.maps.places.PlacesService | null>(null);
    const autocompleteServiceRef = useRef<google.maps.places.AutocompleteService | null>(null);
    const dummyDivRef = useRef<HTMLDivElement>(null);
    const debounceTimeout = useRef<NodeJS.Timeout | null>(null);

    // Initialize Services
    useEffect(() => {
        if (isLoaded && !autocompleteServiceRef.current && window.google) {
            autocompleteServiceRef.current = new window.google.maps.places.AutocompleteService();
        }
        if (isLoaded && !placesServiceRef.current && window.google && dummyDivRef.current) {
            placesServiceRef.current = new window.google.maps.places.PlacesService(dummyDivRef.current);
        }
    }, [isLoaded]);

    // Sync internal state with external value prop
    useEffect(() => {
        setQuery(value);
        if (value && value === query) {
            setIsValidSelection(true);
        } else if (!value) {
            setIsValidSelection(false);
        }
    }, [value]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const fetchPredictions = (input: string) => {
        if (!input.trim()) {
            setPredictions([]);
            return;
        }

        // Static Data Fallback (e.g. Airports) — synchronous, no loading state needed
        if (data && data.length > 0) {
            const filtered = data.filter(item =>
                item.label.toLowerCase().includes(input.toLowerCase())
            );
            setPredictions(filtered);
            setIsLoading(false);
            return;
        }

        // Google Places
        if (!autocompleteServiceRef.current) return;

        setIsLoading(true);
        const request: google.maps.places.AutocompletionRequest = {
            input,
            types: placeTypes
        };

        autocompleteServiceRef.current.getPlacePredictions(request, (results, status) => {
            setIsLoading(false);
            if (status === google.maps.places.PlacesServiceStatus.OK && results) {
                const formatted = results.map(place => ({
                    label: place.description,
                    placeId: place.place_id,
                    lat: 0, // Placeholder, fetch on select
                    lng: 0
                }));
                setPredictions(formatted);
            } else {
                setPredictions([]);
            }
        });
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setQuery(val);
        onChange(val, undefined);
        setIsValidSelection(false);
        setIsOpen(true);
        // Only show spinner for Google Places (async). Static data is synchronous.
        if (!data || data.length === 0) {
            setIsLoading(true);
        }

        if (debounceTimeout.current) clearTimeout(debounceTimeout.current);

        debounceTimeout.current = setTimeout(() => {
            fetchPredictions(val);
        }, 500);
    };

    const handleSelect = (item: LocationData) => {
        console.log("Autocomplete: Selected item", item);
        setQuery(item.label);
        setIsOpen(false);
        setIsValidSelection(true);

        // If static data or already has coords
        if (item.lat !== 0 || !item.placeId || !placesServiceRef.current) {
            console.log("Autocomplete: Using existing coords/static data", { lat: item.lat, lng: item.lng });
            onChange(item.label, item);
            return;
        }

        // Fetch Details for Google Place
        setIsLoading(true);
        const request: google.maps.places.PlaceDetailsRequest = {
            placeId: item.placeId,
            fields: ['geometry', 'name', 'formatted_address']
        };

        placesServiceRef.current.getDetails(request, (place, status) => {
            setIsLoading(false);
            console.log("Autocomplete: Places Details Response", { status, place });
            if (status === google.maps.places.PlacesServiceStatus.OK && place && place.geometry && place.geometry.location) {
                const detailedLocation: LocationData = {
                    label: item.label, // Keep original description or use place.formatted_address
                    lat: place.geometry.location.lat(),
                    lng: place.geometry.location.lng(),
                    placeId: item.placeId
                };
                console.log("Autocomplete: Resolved Coordinates", detailedLocation);
                onChange(item.label, detailedLocation);
            } else {
                console.error("Failed to get place details", status);
                // Proceed with label but no coords? Or error?
                onChange(item.label, undefined);
            }
        });
    };

    return (
        <div className={`relative ${className} ${disabled ? 'opacity-70 pointer-events-none' : ''}`} ref={wrapperRef}>
            {/* Hidden div for PlacesService */}
            <div ref={dummyDivRef} style={{ display: 'none' }}></div>

            {label && (
                <label className="block text-sm font-medium text-gray-700 mb-1.5 pl-0.5">
                    {label}
                </label>
            )}
            <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">
                    {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin text-primary-500" />
                    ) : (
                        icon || <Search className="w-4 h-4" />
                    )}
                </div>
                <Input
                    type="text"
                    value={query}
                    onChange={handleInputChange}
                    onFocus={() => { if (!disabled && query && predictions.length > 0) setIsOpen(true); }}
                    placeholder={placeholder}
                    className={`pl-10 transition-colors ${isValidSelection ? 'border-green-500 bg-green-50/10 focus:ring-green-200 focus:border-green-500' : ''}`}
                    disabled={disabled}
                />
                {isValidSelection && !isLoading && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 text-green-500 pointer-events-none animate-in fade-in zoom-in duration-200">
                        <Check className="w-4 h-4" />
                    </div>
                )}
            </div>

            {isOpen && (predictions.length > 0 || (isLoading && predictions.length === 0 && !data.length)) && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-100 rounded-lg shadow-lg max-h-60 overflow-y-auto animate-in fade-in zoom-in-95 duration-100">
                    <ul className="py-1">
                        {predictions.map((item, id) => (
                            <li
                                key={item.placeId || id}
                                onClick={() => handleSelect(item)}
                                className="px-4 py-2.5 hover:bg-primary-50 cursor-pointer flex items-center gap-3 text-sm text-gray-700 transition-colors"
                            >
                                <MapPin className="w-4 h-4 text-gray-400 shrink-0" />
                                <span>{item.label}</span>
                            </li>
                        ))}
                        {predictions.length === 0 && !isLoading && (
                            <li className="px-4 py-2.5 text-sm text-gray-500">No results found</li>
                        )}
                    </ul>
                </div>
            )}
        </div>
    );
}
