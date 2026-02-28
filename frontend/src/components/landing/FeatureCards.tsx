"use client";

import { motion } from "framer-motion";

const features = [
    {
        title: "Interactive Itinerary Builder",
        description: "Build detailed day-by-day plans with ease. Add activities, flights, and hotels to create the perfect flow for your clients."
    },
    {
        title: "Live Client View & Maps",
        description: "Share beautiful, mobile-friendly itineraries with your clients, complete with interactive real-time maps and routing."
    },
    {
        title: "Centralized Dashboard",
        description: "Keep track of all your trips in one place. Monitor active trips, upcoming departures, and trips needing attention."
    },
    {
        title: "Real-Time Alerts",
        description: "Instantly notify clients of flight delays and manage live disruptions in one workspace."
    },
    {
        title: "AI Resolution Engine",
        description: "Our AI analyzes issues, suggests smart alternatives, and updates plans automatically."
    },
    {
        title: "Smart Notifications",
        description: "Clients and agents get instant status updates from pending to completely resolved."
    }
];

export default function FeatureCards() {
    return (
        <section className="py-24 relative z-10 overflow-hidden" id="features">
            {/* Blue Tone Overlay Gradient */}
            <div className="absolute inset-0 bg-black/20 -z-10" />

            <div className="container px-4 md:px-6 mx-auto relative z-20">
                <div className="text-center mb-16">
                    <h2 className="text-4xl font-bold text-white mb-4 drop-shadow-md">Built for Real Travel Workflows</h2>
                    <p className="text-white/90 max-w-2xl mx-auto text-lg font-medium drop-shadow-sm">Everything you need to manage trips professionally and efficiently.</p>
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{ duration: 0.6 }}
                    className="grid grid-cols-1 md:grid-cols-3 gap-8"
                >
                    {features.map((feature, index) => (
                        <div
                            key={index}
                            className="h-full bg-black/30 backdrop-blur-md p-8 rounded-2xl border border-white/20 shadow-2xl hover: transition-all flex flex-col items-start gap-4 group">
                            <h3 className="text-2xl font-bold text-white mb-2">{feature.title}</h3>
                            <p className="text-white/80 leading-relaxed font-medium flex-grow">
                                {feature.description}
                            </p>
                        </div>
                    ))}
                </motion.div>
            </div>
        </section>
    );
}
