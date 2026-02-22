"use client";

import { useState } from "react";
import { Hotel, Plus, Trash, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import AutocompleteInput from "@/components/ui/AutocompleteInput";
import { searchLocations } from "@/lib/locationService";
import { motion, AnimatePresence } from "framer-motion";

export interface Stay {
    id: number;
    hotelName: string;
    checkIn: string;
    checkOut: string;
    notes: string;
    lat?: number;
    lng?: number;
}

interface HotelStaysProps {
    stays: Stay[];
    onChange: (stays: Stay[]) => void;
}

export default function HotelStays({ stays, onChange }: HotelStaysProps) {
    const [expandedId, setExpandedId] = useState<number | null>(stays[0]?.id || null);

    const addStay = () => {
        const newId = Date.now() + Math.floor(Math.random() * 10000);
        const newStay: Stay = {
            id: newId,
            hotelName: "",
            checkIn: "",
            checkOut: "",
            notes: ""
        };
        onChange([...stays, newStay]);
        setExpandedId(newId);
    };

    const removeStay = (id: number) => {
        onChange(stays.filter(s => s.id !== id));
    };

    const updateStay = (id: number, field: keyof Stay, value: string | number | undefined) => {
        onChange(stays.map(s => s.id === id ? { ...s, [field]: value } : s));
    };

    const toggleExpand = (id: number) => {
        setExpandedId(expandedId === id ? null : id);
    };

    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-6">
            <div className="flex justify-between items-center">
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                    Hotel Stays
                </h2>
                <Button onClick={addStay} size="sm" variant="outline" className="border-dashed">
                    <Plus className="w-4 h-4 mr-2" />
                    Add Stay
                </Button>
            </div>

            <div className="space-y-4">
                <AnimatePresence>
                    {stays.map((stay, index) => (
                        <motion.div
                            key={stay.id}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, height: 0 }}
                            className="border border-gray-200 rounded-lg overflow-hidden bg-gray-50/50"
                        >
                            <div
                                className="px-4 py-3 bg-white border-b border-gray-100 flex justify-between items-center cursor-pointer hover:bg-gray-50 transition-colors"
                                onClick={() => toggleExpand(stay.id)}
                            >
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-600 flex items-center justify-center">
                                        <Hotel className="w-4 h-4" />
                                    </div>
                                    <div>
                                        <h3 className="font-semibold text-gray-900 text-sm">
                                            {stay.hotelName || `Hotel Stay ${index + 1}`}
                                        </h3>
                                        <div className="text-xs text-gray-500">
                                            {stay.checkIn && stay.checkOut ? `${stay.checkIn} - ${stay.checkOut}` : 'Select dates'}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-red-400 hover:text-red-500 hover:bg-red-50"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            removeStay(stay.id);
                                        }}
                                    >
                                        <Trash className="w-4 h-4" />
                                    </Button>
                                    <div className="w-px h-6 bg-gray-200 mx-1" />
                                    {expandedId === stay.id ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                                </div>
                            </div>

                            {expandedId === stay.id && (
                                <div className="p-4 space-y-4 anime-in slide-in-from-top-2 duration-200">
                                    <AutocompleteInput
                                        label="Hotel Name"
                                        placeholder="Search Hotel (Global)..."
                                        placeTypes={['lodging']}
                                        value={stay.hotelName}
                                        onChange={(val, loc) => {
                                            updateStay(stay.id, 'hotelName', val);
                                            if (loc) {
                                                updateStay(stay.id, 'lat', loc.lat);
                                                updateStay(stay.id, 'lng', loc.lng);
                                            }
                                        }}
                                        icon={<Hotel className="w-4 h-4" />}
                                    />

                                    <div className="grid grid-cols-2 gap-4">
                                        <Input
                                            label="Check-in Date"
                                            type="date"
                                            value={stay.checkIn}
                                            onChange={(e) => updateStay(stay.id, 'checkIn', e.target.value)}
                                        />
                                        <Input
                                            label="Check-out Date"
                                            type="date"
                                            value={stay.checkOut}
                                            onChange={(e) => updateStay(stay.id, 'checkOut', e.target.value)}
                                        />
                                    </div>

                                    <div className="space-y-1.5">
                                        <label className="text-sm font-medium text-gray-700">Notes (Optional)</label>
                                        <textarea
                                            value={stay.notes}
                                            onChange={(e) => updateStay(stay.id, 'notes', e.target.value)}
                                            rows={2}
                                            className="w-full rounded-md border border-gray-200 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all placeholder:text-gray-400"
                                            placeholder="Room preferences, booking reference, amenities..."
                                        />
                                    </div>
                                </div>
                            )}
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
}
