"use client";

import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import AutocompleteInput from "@/components/ui/AutocompleteInput";
import { searchLocations } from "@/lib/locationService";
import { Trash2, MapPin } from "lucide-react";

interface ActivityBlockProps {
    activity: {
        time: string;
        duration?: number;
        title: string;
        location: string;
        notes: string | null;
    };
    onChange: (field: string, value: string | number | undefined) => void;
    onRemove: () => void;
    readOnly?: boolean;
}

// Helper to parse/format time
const parseTime = (timeStr: string) => {
    if (!timeStr) return { time12: '', period: 'AM' };
    const [h, m] = timeStr.split(':').map(Number);
    const period = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return { time12: `${h12}:${m.toString().padStart(2, '0')}`, period };
};

// Generate options for 12h time (1:00 to 12:45)
const TIME_OPTIONS_12H: string[] = [];
for (let i = 1; i <= 12; i++) {
    for (let j = 0; j < 60; j += 15) {
        TIME_OPTIONS_12H.push(`${i}:${j.toString().padStart(2, '0')}`);
    }
}

export default function ActivityBlock({ activity, onChange, onRemove, readOnly = false }: ActivityBlockProps) {
    // Duration input removed as per request

    const { time12, period } = parseTime(activity.time);

    const handleTimeChange = (newTime12: string, newPeriod: string) => {
        if (readOnly) return;
        if (!newTime12) {
            onChange('time', '');
            return;
        }
        const [hStr, mStr] = newTime12.split(':');
        let h = parseInt(hStr);
        const m = parseInt(mStr);

        if (newPeriod === 'PM' && h !== 12) h += 12;
        if (newPeriod === 'AM' && h === 12) h = 0;

        const time24 = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
        onChange('time', time24);
    };

    return (
        <div className={`grid grid-cols-1 md:grid-cols-12 gap-3 items-start bg-white p-4 rounded-lg border border-gray-200 shadow-sm group transition-all ${readOnly ? 'opacity-75 bg-gray-50' : 'hover:border-primary-500/50 hover:shadow-md'}`}>
            <div className="md:col-span-2 flex gap-1">
                <select
                    className="w-1/2 rounded-md border border-gray-200 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all bg-white disabled:bg-gray-100 disabled:text-gray-500"
                    value={time12}
                    onChange={(e) => handleTimeChange(e.target.value, period)}
                    disabled={readOnly}
                >
                    <option value="">Time</option>
                    {TIME_OPTIONS_12H.map((t) => (
                        <option key={t} value={t}>{t}</option>
                    ))}
                </select>
                <select
                    className="w-1/2 rounded-md border border-gray-200 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all bg-white disabled:bg-gray-100 disabled:text-gray-500"
                    value={period}
                    onChange={(e) => handleTimeChange(time12, e.target.value)}
                    disabled={readOnly}
                >
                    <option value="AM">AM</option>
                    <option value="PM">PM</option>
                </select>
            </div>

            <div className="md:col-span-4">
                <Input
                    placeholder="Activity Name"
                    value={activity.title}
                    onChange={(e) => onChange('title', e.target.value)}
                    disabled={readOnly}
                />
            </div>
            <div className="md:col-span-3 relative">
                <AutocompleteInput
                    placeholder="Location"
                    onSearch={searchLocations}
                    value={activity.location}
                    onChange={(val, loc) => {
                        onChange('location', val);
                        if (loc) {
                            onChange('lat', loc.lat);
                            onChange('lng', loc.lng);
                        }
                    }}
                    icon={<MapPin className="w-4 h-4" />}
                    disabled={readOnly}
                />
            </div>
            <div className="md:col-span-2">
                <Input
                    placeholder="Notes"
                    value={activity.notes || ''}
                    onChange={(e) => onChange('notes', e.target.value)}
                    disabled={readOnly}
                />
            </div>
            <div className="md:col-span-1 flex justify-end">
                {!readOnly && (
                    <Button variant="ghost" size="icon" onClick={onRemove} className="text-gray-400 hover:text-red-600 hover:bg-red-50">
                        <Trash2 className="w-4 h-4" />
                    </Button>
                )}
            </div>
        </div>
    );
}
