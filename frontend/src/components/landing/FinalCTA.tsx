"use client";

import { Button } from "@/components/ui/Button";

export default function FinalCTA() {
    return (
        <section className="py-24 bg-white relative overflow-hidden flex items-center justify-center border-t border-gray-100">
            <div className="container px-4 md:px-6 relative z-10 text-center space-y-8">
                <h2 className="text-4xl md:text-6xl font-bold tracking-tight text-gray-900">
                    Ready to Transform Your Agency&apos;s Workflow?
                </h2>
                <p className="text-gray-600 max-w-xl mx-auto text-lg">
                    Don&apos;t just plan trips. Manage the reality of travel with the world&apos;s first AI co-pilot.
                </p>
                <div className="pt-4">
                    <Button size="lg" className="btn-primary rounded-full px-12 h-14 text-lg">
                        Get Started Now
                    </Button>
                </div>
            </div>
        </section>
    );
}
