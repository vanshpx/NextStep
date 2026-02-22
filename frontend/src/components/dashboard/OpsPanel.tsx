"use client";

import { useItinerary, Itinerary } from "@/context/ItineraryContext";
import Link from "next/link";

// ─── Helper ───────────────────────────────────────────────────────────────────

function parseStartDate(dateStr: string): Date | null {
    if (!dateStr) return null;
    const part = dateStr.split(/[–-]/)[0].trim();
    const d = new Date(part);
    return isNaN(d.getTime()) ? null : d;
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

interface AttentionItem { itinerary: Itinerary; issue: string; dot: "red" | "amber"; }

function buildAttentionList(itineraries: Itinerary[]): AttentionItem[] {
    const items: AttentionItem[] = [];
    for (const it of itineraries) {
        if (it.status === "Disrupted") {
            items.push({ itinerary: it, issue: "Disrupted — review booking", dot: "red" });
            continue;
        }
        if (it.status === "Upcoming") {
            const mf = !it.flights || it.flights.length === 0;
            const mh = !it.hotelStays || it.hotelStays.length === 0;
            if (mf && mh) items.push({ itinerary: it, issue: "No flights or hotel added", dot: "amber" });
            else if (mf) items.push({ itinerary: it, issue: "Flight details missing", dot: "amber" });
            else if (mh) items.push({ itinerary: it, issue: "Hotel stay not added", dot: "amber" });
            else {
                const start = parseStartDate(it.date);
                if (start) {
                    const h = (start.getTime() - Date.now()) / 3600000;
                    if (h >= 0 && h <= 24) items.push({ itinerary: it, issue: "Departing within 24 hours", dot: "amber" });
                }
            }
        }
    }
    return items.sort((a, b) => (a.dot === "red" ? -1 : b.dot === "red" ? 1 : 0));
}

function NeedsAttentionCard() {
    const { itineraries, isLoading } = useItinerary();
    const items = buildAttentionList(itineraries);

    return (
        <div style={{
            background: "var(--card-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: 10,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
        }}>
            <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--card-border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                    <h3 className="card-title" style={{ lineHeight: 1.3, margin: 0, color: "#dc2626" }}>Needs Attention</h3>
                    <p className="card-subtitle" style={{ marginTop: 2, marginBottom: 0 }}>Action required</p>
                </div>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626" }} />
            </div>

            <div style={{ flex: 1, overflowY: "auto" }}>
                {isLoading ? (
                    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                        {[1, 2, 3].map(i => <div key={i} style={{ height: 40, background: "#fee2e2", borderRadius: 4 }} />)}
                    </div>
                ) : items.length === 0 ? (
                    <div style={{ padding: "40px 16px", textAlign: "center" }}>
                        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>All trips look good</p>
                    </div>
                ) : (
                    items.map(({ itinerary, issue, dot }) => (
                        <Link
                            key={itinerary.id}
                            href={`/dashboard/edit/${itinerary.id}`}
                            style={{
                                display: "flex", alignItems: "center", gap: 10,
                                padding: "12px 20px",
                                textDecoration: "none",
                                background: "transparent",
                                transition: "background 120ms ease",
                                borderBottom: "1px solid #f9fafb"
                            }}
                            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--page-bg)"; }}
                            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                        >
                            <span style={{
                                width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                                background: "#dc2626",
                            }} />
                            <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}>
                                <p style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {itinerary.c}
                                </p>
                                <p className="row-desc" style={{ margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                                    {issue}
                                </p>
                                <span className="meta" style={{ flexShrink: 0, fontVariantNumeric: "tabular-nums", fontSize: "12px" }}>
                                    {itinerary.date ?? "—"}
                                </span>
                            </div>
                        </Link>
                    ))
                )}
            </div>
        </div>
    );
}

// ─── Active Trips ─────────────────────────────────────────────────────────────
function ActiveTripsCard() {
    const { itineraries, isLoading } = useItinerary();

    const active = itineraries
        .filter(it => it.status === "Active")
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
            background: "var(--card-bg)",
            border: "1px solid var(--card-border)",
            borderRadius: 10,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
        }}>
            <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--card-border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                    <h3 className="card-title" style={{ lineHeight: 1.3, margin: 0, color: "#10b981" }}>Active Trips</h3>
                    <p className="card-subtitle" style={{ marginTop: 2, marginBottom: 0 }}>Trips currently in progress</p>
                </div>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#10b981" }} />
            </div>

            <div style={{ flex: 1, overflowY: "auto" }}>
                {isLoading ? (
                    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                        {[1, 2, 3, 4].map(i => <div key={i} style={{ height: 32, background: "#f3f4f6", borderRadius: 4 }} />)}
                    </div>
                ) : active.length === 0 ? (
                    <div style={{ padding: "40px 16px", textAlign: "center" }}>
                        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No active trips</p>
                    </div>
                ) : (
                    groupOrder.map(label => {
                        const items = groups[label];
                        if (items.length === 0) return null;
                        return (
                            <div key={label}>
                                {items.map(({ it, start }) => (
                                    <Link
                                        key={it.id}
                                        href={`/dashboard/edit/${it.id}`}
                                        style={{
                                            display: "flex", alignItems: "center", gap: 12,
                                            padding: "12px 20px",
                                            textDecoration: "none",
                                            transition: "background 120ms ease",
                                            borderBottom: "1px solid #f9fafb"
                                        }}
                                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--page-bg)"; }}
                                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}
                                    >
                                        <span style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: "#10b981" }} />

                                        <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}>
                                            <p style={{ fontSize: "14px", fontWeight: 600, color: "black", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}>
                                                {it.c}
                                            </p>
                                            <p className="row-desc" style={{ margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                                                {it.d}
                                            </p>

                                            <span className="meta" style={{
                                                textTransform: "uppercase",
                                                marginLeft: "auto", fontVariantNumeric: "tabular-nums",
                                                fontSize: "12px"
                                            }}>
                                                {start.getFullYear() === 9999 ? it.date : start.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                                            </span>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function OpsPanel() {
    return (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, minHeight: 280, marginBottom: 28 }}>
            <NeedsAttentionCard />
            <ActiveTripsCard />
        </div>
    );
}
