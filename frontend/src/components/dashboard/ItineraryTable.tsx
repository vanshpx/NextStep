"use client";

import { Eye, Edit, Copy, ExternalLink, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import { useState, Fragment } from "react";

import { useItinerary } from "@/context/ItineraryContext";

interface ItineraryTableProps {
    title?: string;
    showViewAll?: boolean;
    hideHeader?: boolean;
}

export default function ItineraryTable({ title = "Recent Itineraries", showViewAll = true, hideHeader = false }: ItineraryTableProps) {
    const { itineraries, isLoading, deleteItinerary } = useItinerary();
    const [copiedId, setCopiedId] = useState<number | null>(null);
    const [expandedId, setExpandedId] = useState<number | null>(null);
    const [statusFilter, setStatusFilter] = useState('All');

    const handleCopyLink = (id: number) => {
        const origin = typeof window !== 'undefined' && window.location.origin ? window.location.origin : '';
        navigator.clipboard.writeText(`${origin}/view/${id}`);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const filteredItineraries = itineraries.filter(item => {
        if (statusFilter === 'All') return true;
        return item.status === statusFilter;
    });

    if (isLoading) {
        return (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-8 text-center text-gray-500">
                Loading itineraries...
            </div>
        );
    }

    const tabs = ['All', 'Draft', 'Upcoming', 'Active', 'Completed', 'Disrupted'];

    return (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            {!hideHeader && (
                <div className="px-6 py-4 border-b border-gray-100 flex flex-col sm:flex-row justify-between items-center gap-4 bg-gray-50/50">
                    <h3 className="font-bold text-gray-900">{title}</h3>

                    <div className="flex gap-2 bg-white p-1 rounded-md border border-gray-200 shadow-sm">
                        {tabs.map(tab => (
                            <button
                                key={tab}
                                onClick={() => setStatusFilter(tab)}
                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${statusFilter === tab
                                    ? 'bg-primary-50 text-primary-700'
                                    : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                {tab}
                            </button>
                        ))}
                    </div>

                    {showViewAll && (
                        <Button variant="ghost" size="sm" className="hidden sm:flex text-primary-600 hover:text-primary-700 hover:bg-primary-50">View All</Button>
                    )}
                </div>
            )}

            <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-100">
                    <tr>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Client</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Destination</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Dates</th>
                        <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                    {filteredItineraries.length === 0 ? (
                        <tr>
                            <td colSpan={5} className="px-6 py-8 text-center text-gray-500 text-sm">
                                No itineraries found in this category.
                            </td>
                        </tr>
                    ) : (
                        filteredItineraries.map((item) => (
                            <Fragment key={item.id}>
                                <tr
                                    className={`group transition-colors cursor-pointer ${expandedId === item.id ? 'bg-gray-50' : 'hover:bg-gray-50'}`}
                                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                                >
                                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                                        <div className="flex items-center gap-2">
                                            <div className="text-gray-400">
                                                {expandedId === item.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                            </div>
                                            {item.c}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600">{item.d}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${item.status === 'Active' ? 'bg-green-50 text-green-700 border-green-200' :
                                            item.status === 'Upcoming' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' :
                                                item.status === 'Draft' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                                                    item.status === 'Completed' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                                                        item.status === 'Disrupted' ? 'bg-red-50 text-red-700 border-red-200' :
                                                            'bg-gray-100 text-gray-600 border-gray-200'
                                            }`}>
                                            {item.status}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">{item.date}</td>
                                    <td className="px-6 py-4 text-right flex items-center justify-end gap-2 opacity-100 transition-opacity">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            title="Copy Link"
                                            onClick={(e) => { e.stopPropagation(); handleCopyLink(item.id); }}
                                            className={copiedId === item.id ? "text-green-600 bg-green-50" : "text-gray-400 hover:text-primary-600"}
                                        >
                                            {copiedId === item.id ? <ExternalLink className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                        </Button>

                                        {/* View Button Links to Client View */}
                                        <Link href={`/view/${item.id}`} passHref onClick={(e) => e.stopPropagation()}>
                                            <Button variant="ghost" size="icon" title="View" className="text-gray-400 hover:text-primary-600">
                                                <Eye className="w-4 h-4" />
                                            </Button>
                                        </Link>

                                        {/* Edit Button Links to Builder */}
                                        <Link href={`/dashboard/edit/${item.id}`} passHref onClick={(e) => e.stopPropagation()}>
                                            <Button variant="ghost" size="icon" title="Edit" className="text-gray-400 hover:text-primary-600">
                                                <Edit className="w-4 h-4" />
                                            </Button>
                                        </Link>

                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            title="Delete"
                                            className="text-gray-400 hover:text-red-600"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (confirm('Are you sure you want to delete this itinerary?')) {
                                                    deleteItinerary(item.id);
                                                }
                                            }}
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </td>
                                </tr>
                                {expandedId === item.id && (
                                    <tr className="bg-gray-50/50 animate-in fade-in slide-in-from-top-1 duration-200">
                                        <td colSpan={5} className="p-0 border-b border-gray-100">
                                            <div className="mx-4 my-2 p-4 bg-white rounded-lg border border-gray-100 shadow-sm grid grid-cols-1 md:grid-cols-3 gap-6 relative overflow-hidden">

                                                {/* Col 1: Client Bio */}
                                                <div className="flex items-start gap-4">
                                                    <div>
                                                        <h4 className="font-bold text-gray-900 text-sm">{item.c}</h4>
                                                        <div className="text-sm text-gray-500 mt-1 flex items-center gap-2">
                                                            <span>Age: {item.age || "N/A"}</span>
                                                            <span className="w-1 h-1 bg-gray-300 rounded-full" />
                                                            <span>{item.days ? `${item.days} Days` : "Dur. N/A"}</span>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Col 2: Contact Info */}
                                                <div className="space-y-2">
                                                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Contact Details</div>
                                                    <div className="flex flex-col gap-1.5">
                                                        <div className="flex items-center gap-2 text-sm text-gray-700">
                                                            {/* Use Lucide icons or text labels instead of emojis if needed, or just text */}
                                                            <span className="font-medium text-gray-500">Mobile:</span>
                                                            {item.mobile || "N/A"}
                                                        </div>
                                                        <div className="flex items-center gap-2 text-sm text-gray-700">
                                                            <span className="font-medium text-gray-500">Email:</span>
                                                            <a href={`mailto:${item.email}`} className="hover:text-gray-900 transition-colors border-b border-gray-300 hover:border-gray-900 pb-0.5 leading-none">
                                                                {item.email || "N/A"}
                                                            </a>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Col 3: Trip Details */}
                                                <div className="space-y-2">
                                                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Destination</div>
                                                    <div className="flex items-center gap-2 text-sm text-gray-900 mt-2">
                                                        <div className="flex items-center gap-4">
                                                            <span className="font-medium">{item.origin || item.from || "—"}</span>
                                                            <span className="text-gray-400 text-xs">TO</span>
                                                            <span className="font-medium">{item.d}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </Fragment>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
