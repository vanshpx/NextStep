"use client";

import { Home, Map, PlusCircle, LogOut, Layout } from "lucide-react";
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { cn } from "@/lib/utils";

const menuItems = [
    { icon: Home, label: "Dashboard", href: "/dashboard" },
    { icon: PlusCircle, label: "Create Itinerary", href: "/dashboard/create" },
    { icon: Map, label: "All Trips", href: "/dashboard/trips" },
];

export default function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();

    return (
        <aside
            className="flex flex-col h-screen fixed left-0 top-0 z-30"
            style={{ width: 232, background: "var(--sidebar-bg)", borderRight: "1px solid var(--sidebar-border)" }}
        >
            {/* Logo */}
            <div style={{ padding: "20px 16px 16px", borderBottom: "1px solid var(--sidebar-border)", display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 28, height: 28, background: "var(--brand)", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Layout style={{ width: 15, height: 15, color: "#fff" }} />
                </div>
                <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>NexStep</span>
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: "12px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
                {menuItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn("flex items-center transition-all duration-150 sidebar-item")}
                            style={{
                                gap: 10,
                                padding: "8px 12px",
                                paddingLeft: 10,
                                borderRadius: 6,
                                fontSize: "var(--text-md)",
                                fontWeight: isActive ? 520 : 500,
                                color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                                background: isActive ? "#f1f1ef" : "transparent",
                                textDecoration: "none",
                                borderLeft: "3px solid transparent",
                            }}
                            onMouseEnter={e => {
                                if (!isActive) (e.currentTarget as HTMLElement).style.background = "var(--hover-bg)";
                            }}
                            onMouseLeave={e => {
                                if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
                            }}
                        >
                            <item.icon style={{ width: 18, height: 18, flexShrink: 0, color: isActive ? "var(--text-primary)" : "var(--text-muted)" }} />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* Logout */}
            <div style={{ padding: "12px 8px", borderTop: "1px solid var(--sidebar-border)" }}>
                <button
                    onClick={() => router.push('/')}
                    style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "8px 12px", paddingLeft: 13,
                        width: "100%", borderRadius: 6,
                        fontSize: 13, fontWeight: 400,
                        color: "var(--text-tertiary)",
                        background: "transparent", border: "none", cursor: "pointer",
                        transition: "background 120ms ease, color 120ms ease",
                    }}
                    onMouseEnter={e => {
                        (e.currentTarget as HTMLElement).style.background = "#fee2e2";
                        (e.currentTarget as HTMLElement).style.color = "#dc2626";
                    }}
                    onMouseLeave={e => {
                        (e.currentTarget as HTMLElement).style.background = "transparent";
                        (e.currentTarget as HTMLElement).style.color = "var(--text-tertiary)";
                    }}
                >
                    <LogOut style={{ width: 18, height: 18 }} />
                    Logout
                </button>
            </div>
        </aside>
    );
}
