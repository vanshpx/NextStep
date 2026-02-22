import ItineraryTable from "@/components/dashboard/ItineraryTable";
import OpsPanel from "@/components/dashboard/OpsPanel";
import { Button } from "@/components/ui/Button";
import { Plus } from "lucide-react";
import Link from 'next/link';

export default function DashboardPage() {
    return (
        <div>
            {/* Header — title + new button only */}
            <div className="flex justify-between items-center" style={{ marginBottom: 20 }}>
                <h1 style={{
                    fontSize: "var(--text-2xl)",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    margin: 0,
                    letterSpacing: "-0.01em"
                }}>Dashboard</h1>
                <Link href="/dashboard/create">
                    <Button className="btn-primary flex items-center gap-2">
                        <Plus className="w-4 h-4" />
                        New Itinerary
                    </Button>
                </Link>
            </div>


            {/* Operations panels: Needs Attention + Upcoming Timeline */}
            <OpsPanel />

            {/* Itinerary Table */}
            <div style={{ marginTop: 28 }}>
                <ItineraryTable />
            </div>
        </div>
    );
}
