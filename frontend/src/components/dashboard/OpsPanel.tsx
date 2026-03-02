"use client";

import { useItinerary, Itinerary } from "@/context/ItineraryContext";
import Link from "next/link";
import { Wrench, Eye } from "lucide-react";
import { useState, useEffect } from "react";

// ─── Helper ───────────────────────────────────────────────────────────────────

function parseStartDate(dateStr: string): Date | null {
    if (!dateStr) return null;
    const part = dateStr.split(/[–-]/)[0].trim();
    const d = new Date(part);
    return isNaN(d.getTime()) ? null : d;
}

function parseDateRange(dateStr: string) {
    if (!dateStr) return null;
    const parts = dateStr.split(/[–-]/);
    if (parts.length === 0) return null;
    const start = new Date(parts[0].trim());
    if (isNaN(start.getTime())) return null;

    let end = start;
    if (parts.length > 1) {
        let endStr = parts[1].trim();
        const parsedEnd = new Date(endStr);
        if (!isNaN(parsedEnd.getTime())) {
            end = parsedEnd;
        } else {
            const dayMatch = endStr.match(/^\d+/);
            if (dayMatch) {
                end = new Date(start);
                end.setDate(parseInt(dayMatch[0]));
            }
        }
    }
    return { start, end };
}

function parseSearchDate(query: string) {
    const spacedQuery = query.replace(/([a-zA-Z]+)(\d+)/g, '$1 $2');
    const d = new Date(spacedQuery);
    return isNaN(d.getTime()) ? null : d;
}

function matchesSearch(it: Itinerary, query: string): boolean {
    if (!query) return true;
    const q = query.toLowerCase();
    const qNoSpaces = q.replace(/\s+/g, '');

    // Client matching
    if (it.c.toLowerCase().includes(q) || it.c.toLowerCase().replace(/\s+/g, '').includes(qNoSpaces)) return true;

    // Destination matching
    if (it.d.toLowerCase().includes(q) || it.d.toLowerCase().replace(/\s+/g, '').includes(qNoSpaces)) return true;

    // Date matching (string)
    if (it.date && (it.date.toLowerCase().includes(q) || it.date.toLowerCase().replace(/\s+/g, '').includes(qNoSpaces))) return true;

    // Date matching (range logic)
    if (it.date) {
        const searchDate = parseSearchDate(query);
        const range = parseDateRange(it.date);
        if (searchDate && range) {
            const s = new Date(range.start.getFullYear(), range.start.getMonth(), range.start.getDate());
            const e = new Date(range.end.getFullYear(), range.end.getMonth(), range.end.getDate());
            const t = new Date(searchDate.getFullYear(), searchDate.getMonth(), searchDate.getDate());
            if (t.getTime() >= s.getTime() && t.getTime() <= e.getTime()) return true;
        }
    }

    return false;
}

function dayLabel(date: Date): "Today" | "Tomorrow" | "Later" {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diff = Math.round((target.getTime() - today.getTime()) / 86400000);
    if (diff === 0) return "Today";
    if (diff === 1) return "Tomorrow";
    return "Later";
}

// ─── Needs Attention ──────────────────────────────────────────────────────────

interface AttentionItem { 
    itinerary: Itinerary; 
    issue: string; 
    dot: "red" | "amber";
    timestamp?: string;
    isRecent?: boolean;
}

function buildAttentionList(itineraries: Itinerary[]): AttentionItem[] {
    const items: AttentionItem[] = [];
    const now = Date.now();
    const twentyFourHoursAgo = now - (24 * 60 * 60 * 1000);
    
    for (const it of itineraries) {
        if (it.status === "Disrupted") {
            const isRecent = it.updatedAt && new Date(it.updatedAt).getTime() > twentyFourHoursAgo;
            const timestamp = it.updatedAt ? new Date(it.updatedAt).toLocaleString() : 'Unknown';
            
            items.push({ 
                itinerary: it, 
                issue: it.issueSummary || "Issue reported", 
                dot: "red",
                timestamp,
                isRecent 
            });
            continue;
        }
        if (it.status === "Upcoming") {
            const mf = !it.flights || it.flights.length === 0;
            if (mf) {
                items.push({ itinerary: it, issue: "Flight details missing", dot: "amber" });
            } else {
                const start = parseStartDate(it.date);
                if (start) {
                    const h = (start.getTime() - Date.now()) / 3600000;
                    if (h >= 0 && h <= 24) items.push({ itinerary: it, issue: "Departing within 24 hours", dot: "amber" });
                }
            }
        }
    }
    
    // Sort: recent disruptions first, then by dot color
    return items.sort((a, b) => {
        if (a.isRecent && !b.isRecent) return -1;
        if (!a.isRecent && b.isRecent) return 1;
        return (a.dot === "red" ? -1 : b.dot === "red" ? 1 : 0);
    });
}

function NeedsAttentionCard() {
    const { itineraries, isLoading, searchQuery } = useItinerary();
    const items = buildAttentionList(itineraries).filter(item => matchesSearch(item.itinerary, searchQuery));

    return (
        <div style={{
            background: "#ffffff",
            borderWidth: "1px",
            borderStyle: "solid",
            borderColor: "var(--card-border)",
            borderLeft: "3.5px solid #e15959ff",
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
        }}>
            <div style={{ padding: "24px 32px 8px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                    <h3 className="card-title font-bold" style={{ fontSize: "150%", lineHeight: 1.3, margin: 0, color: "#000000", fontFamily: "Roboto, sans-serif" }}>Needs Attention</h3>
                </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "4px 32px 32px" }}>
                {isLoading ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {[1, 2, 3].map(i => <div key={i} style={{ height: 70, background: "var(--page-bg)", borderRadius: 8, opacity: 0.5 }} />)}
                    </div>
                ) : items.length === 0 ? (
                    <div style={{ padding: "40px 16px", textAlign: "center" }}>
                        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>All trips look good</p>
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {items.map(({ itinerary, issue, dot, timestamp, isRecent }) => {
                            return (
                                <div
                                    key={itinerary.id}
                                    style={{
                                        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
                                        padding: "16px",
                                        background: "#fff5f5",
                                        borderRadius: "6px",
                                        boxShadow: "0 1px 3px rgba(0,0,0,0.1)"
                                    }}
                                >
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                            <span style={{ 
                                                width: 8, 
                                                height: 8, 
                                                borderRadius: "50%", 
                                                flexShrink: 0, 
                                                background: dot === "red" ? "#ef4444" : "#f59e0b",
                                                ...(isRecent && dot === "red" && { animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" })
                                            }} />
                                            <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                {itinerary.c} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>• {itinerary.d}</span>
                                            </p>
                                            {isRecent && (
                                                <span style={{ 
                                                    fontSize: "10px", 
                                                    background: "#fee2e2", 
                                                    color: "#991b1b", 
                                                    padding: "2px 6px", 
                                                    borderRadius: "4px",
                                                    fontWeight: 600,
                                                    textTransform: "uppercase"
                                                }}>NEW</span>
                                            )}
                                        </div>
                                        <p style={{ fontSize: "13px", color: "#000000", margin: 0, paddingLeft: 16, display: "flex", alignItems: "center", gap: 6 }}>
                                            <span style={{ fontWeight: 600 }}>Issue:</span>
                                            {issue}
                                            {timestamp && <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>• {timestamp}</span>}
                                        </p>
                                    </div>

                                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                        <Link
                                            href={`/dashboard/edit/${itinerary.id}`}
                                            className="text-gray-400 hover:text-red-500 transition-colors p-2"
                                            title="Edit Itinerary"
                                        >
                                            <Wrench className="w-5 h-5" />
                                        </Link>
                                        <Link
                                            href={`/view/${itinerary.id}`}
                                            target="_blank"
                                            className="text-gray-400 hover:text-primary-600 transition-colors p-2"
                                            title="View Client Page"
                                        >
                                            <Eye className="w-5 h-5" />
                                        </Link>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>
        </div >
    );
}

// ─── Active Trips ─────────────────────────────────────────────────────────────
function ActiveTripsCard() {
    const { itineraries, isLoading, searchQuery } = useItinerary();

    const active = itineraries
        .filter(it => it.status === "Active")
        .filter(it => matchesSearch(it, searchQuery))
        .map(it => {
            // Try dateRange string first, then fall back to Departure flight date
            let start = parseStartDate(it.date);
            if (!start && it.flights && it.flights.length > 0) {
                const dep = it.flights.find(f => f.type === 'Departure');
                if (dep?.date) {
                    const d = new Date(dep.date);
                    if (!isNaN(d.getTime())) start = d;
                }
            }
            // If still no date, place at the end (far future)
            return { it, start: start ?? new Date(9999, 0, 1) };
        })
        .sort((a, b) => a.start.getTime() - b.start.getTime());

    const groups: Record<string, typeof active> = { Today: [], Tomorrow: [], Later: [] };
    for (const item of active) groups[dayLabel(item.start)].push(item);
    const groupOrder: Array<"Today" | "Tomorrow" | "Later"> = ["Today", "Tomorrow", "Later"];

    return (
        <div style={{
            background: "#ffffff",
            borderWidth: "1px",
            borderStyle: "solid",
            borderColor: "var(--card-border)",
            borderLeft: "3.5px solid #1b956cff",
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.1)",
        }}>
            <div style={{ padding: "24px 32px 8px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                    <h3 className="card-title font-bold" style={{ fontSize: "150%", lineHeight: 1.3, margin: 0, color: "#000000", fontFamily: "Roboto, sans-serif" }}>Active Trips</h3>
                </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "4px 32px 32px" }}>
                {isLoading ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {[1, 2, 3, 4].map(i => <div key={i} style={{ height: 80, background: "var(--page-bg)", borderRadius: 8, opacity: 0.5 }} />)}
                    </div>
                ) : active.length === 0 ? (
                    <div style={{ padding: "40px 16px", textAlign: "center" }}>
                        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No active trips</p>
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {groupOrder.map(label => {
                            const items = groups[label];
                            if (items.length === 0) return null;
                            return items.map(({ it }) => {
                                // Calculate current day based on real-time
                                const now = Date.now();
                                const days = it.itineraryDays || [];
                                const totalDays = it.totalDays || days.length || 1;
                                
                                // Get start date from departure flight
                                const startDateRaw = it.flights?.find((f: any) => f.type === 'Departure')?.date || new Date().toISOString();
                                const startDate = new Date(startDateRaw);
                                startDate.setHours(0, 0, 0, 0);
                                
                                // Calculate which day we're on based on current date
                                const today = new Date();
                                today.setHours(0, 0, 0, 0);
                                const daysSinceStart = Math.floor((today.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000));
                                const currentDay = Math.min(Math.max(daysSinceStart + 1, 1), totalDays);
                                
                                // Find current activity based on time
                                const allActivities = days.flatMap((d: any) => 
                                    (d.activities || []).map((a: any) => {
                                        const actDate = new Date(startDate);
                                        actDate.setDate(actDate.getDate() + (d.dayNumber - 1));
                                        if (a.time) {
                                            const parts = a.time.split(':');
                                            if (parts.length === 2) {
                                                actDate.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10), 0, 0);
                                            }
                                        }
                                        // Add 2 hours for activity duration
                                        const endTime = new Date(actDate.getTime() + (2 * 60 * 60 * 1000));
                                        return { ...a, startTime: actDate.getTime(), endTime: endTime.getTime() };
                                    })
                                );
                                
                                // Find first activity that hasn't ended yet
                                const currentActivity = allActivities.find((a: any) => now < a.endTime) || allActivities[allActivities.length - 1];
                                const currentActivityTitle = currentActivity?.title || "Exploring Destination";

                                return (
                                    <div
                                        key={it.id}
                                        style={{
                                            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
                                            padding: "16px",
                                            background: "#f0fdf4",
                                            borderRadius: "6px",
                                            boxShadow: "0 1px 3px rgba(0,0,0,0.1)"
                                        }}
                                    >
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                                <span style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: "var(--success)" }} />
                                                <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                    {it.c} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>• {it.d}</span>
                                                </p>
                                            </div>
                                            <p style={{ fontSize: "13px", margin: 0, paddingLeft: 16, display: "flex", alignItems: "center", gap: 6, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                                                <span style={{ color: "var(--primary-600)", fontWeight: 600, flexShrink: 0 }}>Day {currentDay} of {totalDays}:</span>
                                                <span style={{ color: "var(--text-secondary)", overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>{currentActivityTitle}</span>
                                            </p>
                                        </div>

                                        <Link
                                            href={`/view/${it.id}`}
                                            className="text-gray-400 hover:text-emerald-600 transition-colors p-2"
                                        >
                                            <Eye className="w-5 h-5" />
                                        </Link>
                                    </div>
                                )
                            });
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function OpsPanel() {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return <div style={{ minHeight: 280, marginBottom: 28 }} />;
    }

    return (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, minHeight: 280, marginBottom: 28 }}>
            <NeedsAttentionCard />
            <ActiveTripsCard />
        </div>
    );
}
