"use client";

import { Bell, Search, User } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";

export default function TopBar() {
    const [searchQuery, setSearchQuery] = useState("");

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
                <Button variant="ghost" size="icon" style={{ color: "#6b7280" }} onClick={() => alert("Notifications clicked!")}>
                    <Bell style={{ width: 18, height: 18 }} />
                </Button>

                <div style={{ display: "flex", alignItems: "center", gap: 12, paddingLeft: 16, borderLeft: "1px solid var(--topbar-border)" }}>
                    <div style={{ textAlign: "right" }}>
                        <p style={{ fontSize: "var(--text-md)", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Alex Walker</p>
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
