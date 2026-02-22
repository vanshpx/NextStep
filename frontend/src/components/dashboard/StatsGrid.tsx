"use client";

import { motion } from "framer-motion";
import { Users, Plane, CheckCircle, FileText } from "lucide-react";
import { useItinerary } from "@/context/ItineraryContext";

export default function StatsGrid() {
    const { itineraries, isLoading } = useItinerary();

    // Calculate Stats
    const total = itineraries.length;
    const active = itineraries.filter(i => i.status === 'Active').length;
    const upcoming = itineraries.filter(i => i.status === 'Upcoming').length;
    const completed = itineraries.filter(i => i.status === 'Completed').length;
    const drafts = itineraries.filter(i => i.status === 'Draft').length;

    const stats = [
        { label: "Total Itineraries", value: total.toString(), icon: Users, color: "text-blue-600", bg: "bg-blue-50" },
        { label: "Active Trips", value: active.toString(), icon: Plane, color: "text-cyan-600", bg: "bg-cyan-50" },
        { label: "Upcoming", value: upcoming.toString(), icon: CheckCircle, color: "text-indigo-600", bg: "bg-indigo-50" },
        { label: "Completed", value: completed.toString(), icon: CheckCircle, color: "text-green-600", bg: "bg-green-50" },
        { label: "Drafts", value: drafts.toString(), icon: FileText, color: "text-gray-600", bg: "bg-gray-50" },
    ];

    if (isLoading) {
        return <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6 mb-8 animate-pulse">
            {[1, 2, 3, 4, 5].map(i => <div key={i} className="h-32 bg-gray-100 rounded-xl"></div>)}
        </div>
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6 mb-8">
            {stats.map((stat, index) => (
                <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    whileHover={{ y: -5 }}
                    className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm hover:shadow-lg transition-all cursor-pointer group"
                >
                    <div className="flex justify-between items-start">
                        <div>
                            <p className="text-gray-500 text-sm font-medium mb-1">{stat.label}</p>
                            <h3 className="text-3xl font-bold text-gray-900 group-hover:text-primary-600 transition-colors">{stat.value}</h3>
                        </div>
                        <div className={`p-3 rounded-lg ${stat.bg} ${stat.color}`}>
                            <stat.icon className="w-6 h-6" />
                        </div>
                    </div>
                </motion.div>
            ))}
        </div>
    );
}
