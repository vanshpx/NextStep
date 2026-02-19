import ItineraryTable from "@/components/dashboard/ItineraryTable";
import StatsGrid from "@/components/dashboard/StatsGrid";
import { Button } from "@/components/ui/Button";
import { Plus } from "lucide-react";
import Link from 'next/link';

export default function DashboardPage() {
    return (
        <div className="space-y-8">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
                    <p className="text-gray-500">Welcome back, Alex. Here&apos;s what&apos;s happening today.</p>
                </div>
                <Link href="/dashboard/create">
                    <Button className="btn-primary flex items-center gap-2">
                        <Plus className="w-4 h-4" />
                        New Itinerary
                    </Button>
                </Link>
            </div>

            <StatsGrid />
            <ItineraryTable />
        </div>
    );
}
