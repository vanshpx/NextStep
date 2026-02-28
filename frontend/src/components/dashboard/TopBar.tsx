"use client";

import { Bell, Search, User } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { useItinerary } from "@/context/ItineraryContext";
import Link from "next/link";

export default function TopBar() {
    const { searchQuery, setSearchQuery, itineraries } = useItinerary();
    const [isNotifOpen, setIsNotifOpen] = useState(false);
    const notifRef = useRef<HTMLDivElement>(null);

    const disrupted = itineraries.filter(it => it.status === "Disrupted");

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
                setIsNotifOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    return (
        <header style={{
            height: 56,
            background: "var(--topbar-bg)",
            borderBottom: "1px solid var(--topbar-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 24px",
            position: "sticky",
            top: 0,
            zIndex: 20,
            boxShadow: "0 1px 2px rgba(16,24,40,0.02)",
        }}>
            {/* Product search */}
            <div style={{ position: "relative", width: 320 }}>
                <Search style={{
                    position: "absolute",
                    left: 10,
                    top: "50%",
                    transform: "translateY(-50%)",
                    width: 15,
                    height: 15,
                    color: "#9ca3af",
                    pointerEvents: "none",
                }} />
                <input
                    type="text"
                    placeholder="Search trips, clients…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{
                        width: "100%",
                        height: 40,
                        paddingLeft: 38,
                        paddingRight: 12,
                        background: "#ffffff",
                        border: "1px solid var(--topbar-border)",
                        borderRadius: 6,
                        fontSize: "14px",
                        fontWeight: 500,
                        color: "var(--text-primary)",
                        outline: "none",
                        transition: "border-color 150ms ease, box-shadow 150ms ease",
                    }}
                    onFocus={e => {
                        e.currentTarget.style.borderColor = "var(--brand)";
                        e.currentTarget.style.boxShadow = "0 0 0 2px rgba(37, 99, 235, 0.06)";
                    }}
                    onBlur={e => {
                        e.currentTarget.style.borderColor = "var(--topbar-border)";
                        e.currentTarget.style.boxShadow = "none";
                    }}
                />
            </div>

            {/* Right: actions + user */}
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                {/* Notifications Popup */}
                <div style={{ position: "relative" }} ref={notifRef}>
                    <Button variant="ghost" size="icon" style={{ color: "#6b7280", position: "relative" }} onClick={() => setIsNotifOpen(!isNotifOpen)}>
                        <Bell style={{ width: 18, height: 18 }} />
                        {disrupted.length > 0 && (
                            <span style={{
                                position: "absolute",
                                top: 6,
                                right: 8,
                                width: 8,
                                height: 8,
                                background: "var(--danger)",
                                borderRadius: "50%",
                                border: "2px solid var(--topbar-bg)"
                            }} />
                        )}
                    </Button>

                    {isNotifOpen && (
                        <div style={{
                            position: "absolute",
                            top: "100%",
                            right: 0,
                            marginTop: 8,
                            width: 320,
                            background: "#ffffff",
                            borderRadius: 8,
                            boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
                            border: "1px solid var(--card-border)",
                            zIndex: 50,
                            overflow: "hidden",
                        }}>
                            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--card-border)", background: "#f9fafb" }}>
                                <h4 style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)", fontSize: 14 }}>Notifications</h4>
                            </div>
                            <div style={{ maxHeight: 300, overflowY: "auto" }}>
                                {disrupted.length === 0 ? (
                                    <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                                        No new notifications
                                    </div>
                                ) : (
                                    disrupted.map(it => (
                                        <Link
                                            key={it.id}
                                            href={`/dashboard/edit/${it.id}`}
                                            style={{
                                                padding: "12px 16px",
                                                borderBottom: "1px solid var(--card-border)",
                                                display: "flex",
                                                flexDirection: "column",
                                                gap: 4,
                                                textDecoration: "none",
                                                transition: "background 0.2s"
                                            }}
                                            onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                                            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                                            onClick={() => setIsNotifOpen(false)}
                                        >
                                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                                <p style={{ margin: 0, fontWeight: 500, fontSize: 14, color: "var(--text-primary)" }}>{it.c}</p>
                                                <span style={{ fontSize: 11, color: "#ef4444", background: "#fef2f2", padding: "2px 6px", borderRadius: 4, fontWeight: 500 }}>Disruptions</span>
                                            </div>
                                            <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
                                                Trip to {it.d} has disruptions.
                                            </p>
                                        </Link>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 12, paddingLeft: 16, borderLeft: "1px solid var(--topbar-border)" }}>
                    <div style={{ textAlign: "right" }}>
                        <p style={{ fontSize: "var(--text-md)", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Aman Sharma</p>
                        <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)", fontWeight: 400, margin: 0 }}>Senior Agent</p>
                    </div>
                    <button
                        onClick={() => alert("Profile settings")}
                        style={{
                            width: 34,
                            height: 34,
                            borderRadius: "50%",
                            background: "var(--page-bg)",
                            border: "1px solid var(--topbar-border)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            cursor: "pointer",
                        }}
                    >
                        <User style={{ width: 16, height: 16, color: "var(--text-secondary)" }} />
                    </button>
                </div>
            </div>
        </header>
    );
}
