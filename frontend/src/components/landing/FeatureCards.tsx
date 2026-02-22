"use client";

import { motion } from "framer-motion";
import { Layers, Activity, Zap } from "lucide-react";

const features = [
    {
        icon: <Layers className="w-8 h-8 text-primary-600" />,
        title: "Itinerary Builder",
        description: "Build detailed day-by-day plans with ease. Drag, drop, and organize to create the perfect flow for your clients."
    },
    {
        icon: <Activity className="w-8 h-8 text-primary-600" />,
        title: "Trip Monitoring",
        description: "Keep track of every active trip in real-time. Dashboard summaries help you stay ahead of any schedule changes."
    },
    {
        icon: <Zap className="w-8 h-8 text-primary-600" />,
        title: "Disruption Reporting",
        description: "Quickly log and manage disruptions like flight delays or cancellations directly from the client view."
    }
];

export default function FeatureCards() {
    return (
        <section className="py-24 bg-gray-50 relative z-10" id="features">
            <div className="container px-4 md:px-6 mx-auto">
                <div className="text-center mb-16">
                    <h2 className="text-3xl font-bold text-gray-900 mb-4">Built for Real Travel Workflows</h2>
                    <p className="text-gray-600 max-w-2xl mx-auto">Everything you need to manage trips professionally and efficiently.</p>
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
                            className="bg-white p-8 rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow flex flex-col items-start gap-4"
                        >
                            <div className="p-3 rounded-lg bg-primary-50">
                                {feature.icon}
                            </div>
                            <h3 className="text-xl font-bold text-gray-900">{feature.title}</h3>
                            <p className="text-gray-600 leading-relaxed">
                                {feature.description}
                            </p>
                        </div>
                    ))}
                </motion.div>
            </div>
        </section>
    );
}
