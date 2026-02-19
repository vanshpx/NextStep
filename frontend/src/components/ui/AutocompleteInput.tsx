"use client";

import { useState, useEffect, useRef } from "react";
import { MapPin, Search, Check, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/Input";

export interface LocationData {
    label: string;
    lat: number;
    lng: number;
}

interface AutocompleteInputProps {
    label?: string;
    placeholder?: string;
    data?: LocationData[]; // Static list
    onSearch?: (query: string) => Promise<LocationData[]>; // Async search
    value?: string;
    onChange: (value: string, location?: LocationData) => void;
    className?: string;
    icon?: React.ReactNode;
    disabled?: boolean;
}

export default function AutocompleteInput({
    label,
    placeholder = "Search...",
    data = [],
    onSearch,
    value = "",
    onChange,
    className = "",
    icon,
    disabled = false
}: AutocompleteInputProps) {
    const [query, setQuery] = useState(value);
    const [isOpen, setIsOpen] = useState(false);
    const [filteredData, setFilteredData] = useState<LocationData[]>([]);
    const [isValidSelection, setIsValidSelection] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);
    const debounceTimeout = useRef<NodeJS.Timeout | null>(null);

    // Sync internal state with external value prop
    useEffect(() => {
        setQuery(value);
    }, [value]);

    useEffect(() => {
        // Validate selection based on whether the current query matches a known item
        // This is heuristic; for async, strictly we rely on the user selecting an item.
        // But for display perposes, if query === value passed in, we can assume valid if value was set via selection.
        // A better check:
        setIsValidSelection(!!value && query === value);
    }, [value, query]);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const fetchResults = async (userInput: string) => {
        if (!userInput.trim()) {
            setFilteredData([]);
            return;
        }

        setIsLoading(true);

        try {
            if (onSearch) {
                const results = await onSearch(userInput);
                setFilteredData(results);
            } else {
                // Fallback to static data filtering
                const filtered = data.filter(item =>
                    item.label.toLowerCase().includes(userInput.toLowerCase())
                );
                setFilteredData(filtered);
            }
        } catch (error) {
            console.error("Search failed:", error);
            setFilteredData([]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const userInput = e.target.value;
        setQuery(userInput);
        onChange(userInput, undefined); // Clear location data on manual type
        setIsValidSelection(false);
        setIsOpen(true);

        if (debounceTimeout.current) {
            clearTimeout(debounceTimeout.current);
        }

        if (userInput.trim() === "") {
            setFilteredData([]);
            setIsOpen(false);
            setIsLoading(false);
            return;
        }

        // Debounce only for async search to save API calls
        // For static data, we can filter immediately or with short debounce
        const delay = onSearch ? 500 : 0;

        debounceTimeout.current = setTimeout(() => {
            fetchResults(userInput);
        }, delay);
    };

    const handleSelect = (item: LocationData) => {
        setQuery(item.label);
        onChange(item.label, item);
        setIsValidSelection(true);
        setIsOpen(false);
    };

    return (
        <div className={`relative ${className} ${disabled ? 'opacity-70 pointer-events-none' : ''}`} ref={wrapperRef}>
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
                    onFocus={() => {
                        if (!disabled && query && filteredData.length > 0) setIsOpen(true);
                    }}
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

            {isOpen && (filteredData.length > 0 || (isLoading && filteredData.length === 0 && onSearch)) && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-100 rounded-lg shadow-lg max-h-60 overflow-y-auto animate-in fade-in zoom-in-95 duration-100">
                    <ul className="py-1">
                        {filteredData.map((item, index) => (
                            <li
                                key={index}
                                onClick={() => handleSelect(item)}
                                className="px-4 py-2.5 hover:bg-primary-50 cursor-pointer flex items-center gap-3 text-sm text-gray-700 transition-colors"
                            >
                                <MapPin className="w-4 h-4 text-gray-400 shrink-0" />
                                <span>{item.label}</span>
                            </li>
                        ))}
                        {filteredData.length === 0 && !isLoading && onSearch && (
                            <li className="px-4 py-2.5 text-sm text-gray-500">No results found</li>
                        )}
                        {filteredData.length === 0 && !isLoading && !onSearch && (
                            <li className="px-4 py-2.5 text-sm text-gray-500">No matching options</li>
                        )}
                    </ul>
                </div>
            )}
        </div>
    );
}
