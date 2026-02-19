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

    const handleLogout = () => {
        // In a real app, clear auth tokens here
        router.push('/');
    };

    return (
        <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-screen fixed left-0 top-0 z-30">
            {/* Logo */}
            <div className="p-6 flex items-center gap-3 border-b border-gray-100">
                <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                    <Layout className="w-5 h-5 text-white" />
                </div>
                <span className="text-xl font-bold text-gray-900 tracking-tight">NexStep</span>
            </div>

            {/* Navigation */}
            <nav className="flex-1 p-4 space-y-2">
                {menuItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group font-medium",
                                isActive
                                    ? "bg-primary-50 text-primary-600 shadow-sm"
                                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                            )}
                        >
                            <item.icon className={cn("w-5 h-5", isActive ? "text-primary-600" : "text-gray-400 group-hover:text-gray-600")} />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* User & Logout */}
            <div className="p-4 border-t border-gray-100">
                <button
                    onClick={handleLogout}
                    className="flex items-center gap-3 px-4 py-3 w-full rounded-lg text-gray-600 hover:bg-red-50 hover:text-red-600 transition-all group font-medium"
                >
                    <LogOut className="w-5 h-5 group-hover:text-red-600 text-gray-400" />
                    Logout
                </button>
            </div>
        </aside>
    );
}
