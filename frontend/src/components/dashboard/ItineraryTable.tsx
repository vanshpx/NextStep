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
        <div style={{ background: "var(--card-bg)", borderRadius: 10, border: "1px solid var(--card-border)", overflow: "hidden", boxShadow: "0 1px 2px rgba(16,24,40,0.04)" }}>
            {!hideHeader && (
                <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--card-border)", display: "flex", flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
                    <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>{title}</h3>

                    <div style={{ display: "flex", gap: 2, background: "var(--page-bg)", padding: "3px", borderRadius: 6, border: "1px solid var(--card-border)" }}>
                        {tabs.map(tab => (
                            <button
                                key={tab}
                                onClick={() => setStatusFilter(tab)}
                                style={{
                                    height: 26,
                                    padding: "0 10px",
                                    cursor: "pointer",
                                    transition: "background 120ms ease, color 120ms ease",
                                    background: statusFilter === tab ? "#ffffff" : "transparent",
                                    color: statusFilter === tab ? "var(--brand)" : "var(--text-secondary)",
                                    boxShadow: statusFilter === tab ? "0 1px 2px rgba(0,0,0,0.05)" : "none",
                                    fontWeight: statusFilter === tab ? 600 : 500,
                                }}
                            >
                                {tab}
                            </button>
                        ))}
                    </div>


                </div>
            )}

            <table className="w-full">
                <thead>
                    <tr style={{ borderBottom: "1px solid var(--card-border)" }}>
                        <th className="px-6 py-3 text-left" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Client</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Destination</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Status</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Dates</th>
                        <th className="px-6 py-3 text-right" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Actions</th>
                    </tr>
                </thead>
                <tbody>
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
                                    className="group transition-colors cursor-pointer"
                                    style={{
                                        height: 54,
                                        borderBottom: "1px solid var(--card-border)",
                                        backgroundColor: expandedId === item.id ? "var(--page-bg)" : undefined,
                                    }}
                                    onMouseEnter={e => {
                                        if (expandedId !== item.id)
                                            (e.currentTarget as HTMLElement).style.backgroundColor = "var(--page-bg)";
                                    }}
                                    onMouseLeave={e => {
                                        if (expandedId !== item.id)
                                            (e.currentTarget as HTMLElement).style.backgroundColor = "";
                                    }}
                                    onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                                >
                                    <td className="px-6 table-primary" style={{ fontSize: "var(--text-md)", fontWeight: 520, color: "#0f172a" }}>
                                        <div className="flex items-center gap-2">
                                            <div style={{ color: "#cbd5e1" }}>
                                                {expandedId === item.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                            </div>
                                            {item.c}
                                        </div>
                                    </td>
                                    <td className="px-6" style={{ fontSize: "var(--text-md)", color: "#0f172a", fontWeight: 500 }}>{item.d}</td>
                                    <td className="px-6">
                                        {/* Product-quality status tag */}
                                        <span className="badge" style={{
                                            display: "inline-flex",
                                            alignItems: "center",
                                            padding: "2px 8px",
                                            borderRadius: 6,
                                            fontSize: "var(--text-xs)",
                                            fontWeight: 500,
                                            letterSpacing: "0.01em",
                                            ...(item.status === "Active" ? { background: "var(--success-bg)", color: "var(--success)" } :
                                                item.status === "Upcoming" ? { background: "var(--upcoming-bg)", color: "var(--upcoming)" } :
                                                    item.status === "Draft" ? { background: "var(--draft-bg)", color: "var(--draft)" } :
                                                        item.status === "Completed" ? { background: "var(--completed-bg)", color: "var(--completed)" } :
                                                            item.status === "Disrupted" ? { background: "var(--danger-bg)", color: "var(--danger)" } :
                                                                { background: "var(--page-bg)", color: "var(--text-muted)" })
                                        }}>
                                            {item.status}
                                        </span>
                                    </td>
                                    <td className="px-6 meta" style={{ fontVariantNumeric: "tabular-nums" }}>{item.date}</td>
                                    <td className="px-6 text-right">
                                        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
                                        </div>
                                    </td>
                                </tr>
                                {expandedId === item.id && (
                                    <tr className="bg-gray-50/50 animate-in fade-in slide-in-from-top-1 duration-200">
                                        <td colSpan={5} className="p-0 border-b border-gray-100">
                                            <div className="mx-4 my-2 p-4 bg-white rounded-[6px] border border-gray-100 shadow-sm grid grid-cols-1 md:grid-cols-3 gap-6 relative overflow-hidden">

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
