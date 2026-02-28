"use client";

import { Input } from "@/components/ui/Input";
import AutocompleteInput from "@/components/ui/AutocompleteInput";
import { searchLocations } from "@/lib/locationService";

interface ClientDetailsFormProps {
    formData: {
        clientName: string;
        age: string;
        contact: string;
        origin: string;
        destination: string;
        days: string;
    };
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
    readOnly?: boolean;
}

export default function ClientDetailsForm({ formData, onChange, readOnly = false }: ClientDetailsFormProps) {
    return (
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-8">
            <h2 className="text-xl font-bold mb-4 text-gray-900 flex items-center gap-2">
                Client Details
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">Client Name</label>
                    <Input name="clientName" placeholder="e.g. John Doe" value={formData.clientName} onChange={onChange} disabled={readOnly} />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">Age</label>
                    <Input name="age" placeholder="e.g. 35" type="number" value={formData.age} onChange={onChange} disabled={readOnly} />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">Contact</label>
                    <Input name="contact" placeholder="Email or Phone" value={formData.contact} onChange={onChange} disabled={readOnly} />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">From Location</label>
                    <AutocompleteInput
                        placeholder="Origin City, Town, Village..."
                        placeTypes={['(cities)']}
                        value={formData.origin}
                        onChange={(val) => {
                            // We need to manually construct the event object since AutocompleteInput returns (value, location)
                            // But ClientDetailsForm expects (e) => void. 
                            // This is a bit mismatch. Let's fix the handler in ClientDetailsFormProps or adapter here.
                            // The simplest is to cast or change the prop type, but let's just make a synthetic event.
                            onChange({ target: { name: 'origin', value: val } } as unknown as React.ChangeEvent<HTMLInputElement>);
                        }}
                        disabled={readOnly}
                    />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">Destination</label>
                    <AutocompleteInput
                        placeholder="Target City, Town, Village..."
                        placeTypes={['(cities)']}
                        value={formData.destination}
                        onChange={(val) => {
                            onChange({ target: { name: 'destination', value: val } } as unknown as React.ChangeEvent<HTMLInputElement>);
                        }}
                        disabled={readOnly}
                    />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700">Number of Days</label>
                    <Input name="days" placeholder="Duration" type="number" min="1" value={formData.days} onChange={onChange} disabled={readOnly} />
                </div>
            </div>
        </div>
    );
}
