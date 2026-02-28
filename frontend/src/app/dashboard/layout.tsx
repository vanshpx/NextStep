import Sidebar from "@/components/dashboard/Sidebar";
import TopBar from "@/components/dashboard/TopBar";

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="min-h-screen flex font-sans" style={{ background: "var(--page-bg)" }}>
            <Sidebar />
            <div className="flex-1 flex flex-col min-h-screen" style={{ marginLeft: 232 }}>
                <TopBar />
                <main className="flex-1 p-8 overflow-y-auto">
                    {children}
                </main>
            </div>
        </div>
    );
}
