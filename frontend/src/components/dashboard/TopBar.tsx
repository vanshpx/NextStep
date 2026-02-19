"use client";

import { Bell, Search, User } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { useState } from "react";
import { Button } from "@/components/ui/Button";

export default function TopBar() {
    const [searchQuery, setSearchQuery] = useState("");

    return (
        <header className="h-16 bg-white/90 backdrop-blur-md border-b border-gray-200 flex items-center justify-between px-6 sticky top-0 z-20">
            {/* Search */}
            <div className="relative w-96">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                    className="pl-10 bg-gray-50 border-gray-200 focus:bg-white transition-colors"
                    placeholder="Search trips, clients, or destinations..."
                    value={searchQuery}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
                />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-4">
                <Button variant="ghost" size="icon" className="text-gray-500 hover:text-primary-600" onClick={() => alert("Notifications clicked!")}>
                    <Bell className="w-5 h-5" />
                </Button>

                <div className="flex items-center gap-3 pl-4 border-l border-gray-200">
                    <div className="text-right hidden md:block">
                        <p className="text-sm font-bold text-gray-900">Alex Walker</p>
                        <p className="text-xs text-gray-500">Senior Agent</p>
                    </div>
                    <Button variant="secondary" size="icon" className="rounded-full w-10 h-10 bg-gray-100 border-gray-200" onClick={() => alert("Profile settings")}>
                        <User className="w-5 h-5 text-gray-600" />
                    </Button>
                </div>
            </div>
        </header>
    );
}
