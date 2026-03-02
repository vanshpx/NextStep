"use client";

import { Button } from "@/components/ui/Button";
import Link from "next/link";

export default function FinalCTA() {
    return (
        <section className="py-32 relative overflow-hidden flex items-center justify-center">
            {/* Strong Blue Overlay */}
            <div className="absolute inset-0 bg-black/60 -z-10" />

            <div className="container px-4 md:px-6 relative z-10 text-center space-y-10">
                <h2 className="text-4xl md:text-7xl font-bold tracking-tight text-white drop-shadow-xl">
                    Ready to Transform Your Agency's Workflow?
                </h2>
                <p className="text-white/80 max-w-2xl mx-auto text-xl font-medium drop-shadow-lg">
                    Don't just plan trips. Transform chaos into clarity with AI-powered travel management.
                </p>
                <div className="pt-6">
                    <Link href="/dashboard">
                        <Button variant="ghost" size="lg" className="bg-transparent hover:bg-white text-white rounded-full px-12 h-16 text-xl font-bold border border-white transition-all duration-300 hover:scale-100">
                            Get Started Now
                        </Button>
                    </Link>
                </div>
            </div>
        </section>
    );
}
