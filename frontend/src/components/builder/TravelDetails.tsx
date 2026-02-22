"use client";

import { PlaneTakeoff, PlaneLanding } from "lucide-react";
import { Input } from "@/components/ui/Input";
import AutocompleteInput from "@/components/ui/AutocompleteInput";
import { airports } from "@/lib/mockLocations";

interface TravelInfo {
    date: string;
    airport: string;
    airline: string;
    flightNumber: string;
    departureTime: string;
    arrivalTime: string;
    lat?: number;
    lng?: number;
    arrivalAirport?: string;
    arrivalLat?: number;
    arrivalLng?: number;
}

interface TravelDetailsProps {
    departure: TravelInfo;
    returnTrip: TravelInfo;
    onChange: (type: 'departure' | 'return', field: keyof TravelInfo, value: string | number | undefined) => void;
    disabledDeparture?: boolean;
    disabledReturn?: boolean;
}

export default function TravelDetails({ departure, returnTrip, onChange, disabledDeparture = false, disabledReturn = false }: TravelDetailsProps) {
    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-6">
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                Travel Details
            </h2>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Departure Column */}
                <div className={`space-y-4 ${disabledDeparture ? 'opacity-75 pointer-events-none grayscale-[0.5]' : ''}`}>
                    <div className="flex items-center justify-between text-gray-700 font-semibold border-b border-gray-100 pb-2">
                        <div className="flex items-center gap-2">
                            <PlaneTakeoff className="w-5 h-5 text-primary-600" />
                            Departure
                        </div>
                        {disabledDeparture && <span className="text-xs font-normal text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">Locked (Past)</span>}
                    </div>

                    <AutocompleteInput
                        label="Departure Airport / Station"
                        placeholder="Search Origin..."
                        data={airports}
                        value={departure.airport}
                        onChange={(val, loc) => {
                            onChange('departure', 'airport', val);
                            if (loc) {
                                onChange('departure', 'lat', loc.lat);
                                onChange('departure', 'lng', loc.lng);
                            }
                        }}
                        disabled={disabledDeparture}
                    />

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-700">Date</label>
                        <Input
                            type="date"
                            value={departure.date ?? ""}
                            onChange={(e) => onChange('departure', 'date', e.target.value)}
                            disabled={disabledDeparture}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <Input
                            label="Airline / Train"
                            placeholder="e.g. Emirates"
                            value={departure.airline ?? ""}
                            onChange={(e) => onChange('departure', 'airline', e.target.value)}
                            disabled={disabledDeparture}
                        />
                        <Input
                            label="Flight / Train No."
                            placeholder="e.g. EK501"
                            value={departure.flightNumber ?? ""}
                            onChange={(e) => onChange('departure', 'flightNumber', e.target.value)}
                            disabled={disabledDeparture}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <Input
                            label="Departure Time"
                            type="time"
                            value={departure.departureTime ?? ""}
                            onChange={(e) => onChange('departure', 'departureTime', e.target.value)}
                            disabled={disabledDeparture}
                        />
                        <Input
                            label="Arrival Time"
                            type="time"
                            value={departure.arrivalTime ?? ""}
                            onChange={(e) => onChange('departure', 'arrivalTime', e.target.value)}
                            disabled={disabledDeparture}
                        />
                    </div>
                </div>

                {/* Return Column */}
                <div className={`space-y-4 pt-8 lg:pt-0 lg:border-l lg:border-gray-100 lg:pl-8 ${disabledReturn ? 'opacity-75 pointer-events-none grayscale-[0.5]' : ''}`}>
                    <div className="flex items-center justify-between text-gray-700 font-semibold border-b border-gray-100 pb-2">
                        <div className="flex items-center gap-2">
                            <PlaneLanding className="w-5 h-5 text-primary-600" />
                            Return
                        </div>
                        {disabledReturn && <span className="text-xs font-normal text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">Locked (Past)</span>}
                    </div>

                    <AutocompleteInput
                        label="Return Airport / Station"
                        placeholder="Search Airport..."
                        data={airports}
                        value={returnTrip.airport}
                        onChange={(val, loc) => {
                            onChange('return', 'airport', val);
                            if (loc) {
                                onChange('return', 'lat', loc.lat);
                                onChange('return', 'lng', loc.lng);
                            }
                        }}
                        disabled={disabledReturn}
                    />

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-700">Date</label>
                        <Input
                            type="date"
                            value={returnTrip.date ?? ""}
                            onChange={(e) => onChange('return', 'date', e.target.value)}
                            disabled={disabledReturn}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <Input
                            label="Airline / Train"
                            placeholder="e.g. Emirates"
                            value={returnTrip.airline ?? ""}
                            onChange={(e) => onChange('return', 'airline', e.target.value)}
                            disabled={disabledReturn}
                        />
                        <Input
                            label="Flight / Train No."
                            placeholder="e.g. EK502"
                            value={returnTrip.flightNumber ?? ""}
                            onChange={(e) => onChange('return', 'flightNumber', e.target.value)}
                            disabled={disabledReturn}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <Input
                            label="Departure Time"
                            type="time"
                            value={returnTrip.departureTime ?? ""}
                            onChange={(e) => onChange('return', 'departureTime', e.target.value)}
                            disabled={disabledReturn}
                        />
                        <Input
                            label="Arrival Time"
                            type="time"
                            value={returnTrip.arrivalTime ?? ""}
                            onChange={(e) => onChange('return', 'arrivalTime', e.target.value)}
                            disabled={disabledReturn}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
