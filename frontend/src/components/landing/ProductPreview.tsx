"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { Layout, CheckCircle, Clock } from "lucide-react";

export default function ProductPreview() {
    const ref = useRef(null);
    const { scrollYProgress } = useScroll({
        target: ref,
        offset: ["start end", "end start"]
    });

    const xRight = useTransform(scrollYProgress, [0, 0.5], [100, 0]);
    const opacity = useTransform(scrollYProgress, [0, 0.3], [0, 1]);
    const y = useTransform(scrollYProgress, [0, 0.3], [100, 0]);

    return (
        <section ref={ref} className="py-24 bg-white relative overflow-hidden">
            <div className="container px-4 md:px-6 relative z-10">
                <motion.div
                    style={{ opacity, y }}
                    className="text-center mb-16"
                >
                    <h2 className="text-3xl md:text-5xl font-bold text-gray-900 mb-6">Total Control Center</h2>
                    <p className="text-gray-600 max-w-2xl mx-auto text-lg">
                        A unified dashboard that evolves with your trips. From planning to execution, see everything at a glance.
                    </p>
                </motion.div>

                <div className="relative h-[600px] w-full max-w-6xl mx-auto">
                    {/* Dashboard Mockup (Center) */}
                    <motion.div
                        style={{ y }}
                        className="absolute inset-0 z-20 rounded-xl bg-gray-50 border border-gray-200 shadow-2xl overflow-hidden"
                    >
                        {/* Sidebar */}
                        <div className="absolute left-0 top-0 bottom-0 w-64 bg-white border-r border-gray-200 p-4 flex flex-col gap-4">
                            <div className="flex items-center gap-2 mb-6 px-2">
                                <div className="w-6 h-6 bg-primary-600 rounded-md flex items-center justify-center">
                                    <Layout className="w-3 h-3 text-white" />
                                </div>
                                <span className="font-bold text-gray-900">NexStep</span>
                            </div>
                            <div className="h-8 w-full bg-primary-50 text-primary-700 rounded-md flex items-center px-3 text-sm font-medium">Dashboard</div>
                            <div className="h-8 w-full text-gray-600 rounded-md flex items-center px-3 text-sm font-medium hover:bg-gray-50">Itineraries</div>
                            <div className="h-8 w-full text-gray-600 rounded-md flex items-center px-3 text-sm font-medium hover:bg-gray-50">Settings</div>
                        </div>
                        {/* Main Content */}
                        <div className="absolute left-64 top-0 right-0 bottom-0 p-8 bg-gray-50/50">
                            <div className="flex justify-between items-center mb-8">
                                <div>
                                    <h3 className="text-2xl font-bold text-gray-900">Dashboard</h3>
                                    <p className="text-sm text-gray-500">Welcome back, Alex.</p>
                                </div>
                                <div className="flex gap-4">
                                    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm w-40">
                                        <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                                            <Clock className="w-4 h-4 text-primary-500" />
                                            Active Trips
                                        </div>
                                        <div className="text-2xl font-bold text-gray-900">12</div>
                                    </div>
                                    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm w-40">
                                        <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                                            <CheckCircle className="w-4 h-4 text-green-500" />
                                            Completed
                                        </div>
                                        <div className="text-2xl font-bold text-gray-900">148</div>
                                    </div>
                                </div>
                            </div>
                            {/* Table Mockup */}
                            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                                <div className="h-12 border-b border-gray-100 bg-gray-50/50 flex items-center px-6">
                                    <div className="w-1/4 h-4 bg-gray-200 rounded"></div>
                                </div>
                                <div className="p-6 space-y-4">
                                    {[1, 2, 3].map(i => (
                                        <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                                            <div className="w-1/4 h-4 bg-gray-100 rounded"></div>
                                            <div className="w-1/4 h-4 bg-gray-100 rounded"></div>
                                            <div className="w-20 h-6 bg-green-50 text-green-700 text-xs rounded-full flex items-center justify-center font-medium">Active</div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Floating Element - Status Badge (Right) */}
                    <motion.div
                        style={{ x: xRight, y: -50 }}
                        className="absolute -right-12 top-24 z-30 p-4 rounded-xl bg-white border border-l-4 border-l-primary-500 border-gray-100 shadow-lg"
                    >
                        <div className="flex items-center gap-3">
                            <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
                            <div>
                                <div className="text-xs text-gray-500">Status Update</div>
                                <div className="font-bold text-gray-900">Trip Resolved</div>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </div>
        </section>
    );
}
