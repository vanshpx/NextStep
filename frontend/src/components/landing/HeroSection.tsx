"use client";

import { Button } from "@/components/ui/Button";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, Layout } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";

export default function HeroSection() {
    const ref = useRef(null);
    const { scrollY } = useScroll();
    const y1 = useTransform(scrollY, [0, 500], [0, 200]);

    return (
        <section ref={ref} className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden pt-32 pb-20 bg-white">

            {/* Navigation (simplified for hero) */}
            <nav className="fixed top-0 inset-x-0 z-50 h-20 flex items-center justify-between px-6 lg:px-12 bg-white/80 backdrop-blur-md border-b border-gray-100">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                        <Layout className="w-5 h-5 text-white" />
                    </div>
                    <span className="text-xl font-bold text-gray-900 tracking-tight">NexStep</span>
                </div>

                <div className="flex items-center gap-6">
                    <div className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-600">
                        <a href="#features" className="hover:text-primary-600 transition-colors">Features</a>
                        <a href="#pricing" className="hover:text-primary-600 transition-colors">Pricing</a>
                        <a href="#about" className="hover:text-primary-600 transition-colors">About</a>
                    </div>
                    <Link href="/dashboard">
                        <Button variant="ghost" className="text-gray-600 hover:text-primary-600 font-medium">Log In</Button>
                    </Link>
                    <Link href="/dashboard">
                        <Button className="btn-primary">Get Started</Button>
                    </Link>
                </div>
            </nav>

            <div className="container px-4 md:px-6 relative z-10 text-center">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="max-w-4xl mx-auto space-y-6"
                >
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-50 text-primary-700 text-sm font-medium border border-primary-100 mb-4">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
                        </span>
                        The Future of Travel Planning is Here
                    </div>

                    <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-gray-900">
                        Smart itinerary management <br />
                        <span className="text-primary-600">for modern agents.</span>
                    </h1>

                    <p className="text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed">
                        NexStep brings clarity to travel planning. Create beautiful itineraries, track live trips, and manage disruptions in one professional workspace.
                    </p>

                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
                        <Link href="/dashboard">
                            <Button size="lg" className="btn-primary h-12 px-8 text-lg rounded-full flex items-center gap-2">
                                Start Making Itinerary
                                <ArrowRight className="w-4 h-4" />
                            </Button>
                        </Link>
                        <Button variant="outline" size="lg" className="h-12 px-8 text-lg border-gray-300 text-gray-700 hover:bg-gray-50 rounded-full">
                            Watch Demo
                        </Button>
                    </div>
                </motion.div>

                {/* Mock UI Element */}
                <motion.div
                    style={{ y: y1, rotateX: 5 }}
                    className="mt-20 relative w-full max-w-5xl mx-auto perspective-1000"
                >
                    <div className="relative rounded-xl border border-gray-200 bg-white shadow-2xl overflow-hidden aspect-[16/9] group hover:shadow-3xl transition-shadow duration-500">
                        {/* Browser Header */}
                        <div className="h-12 border-b border-gray-100 flex items-center px-4 gap-2 bg-gray-50">
                            <div className="flex gap-2">
                                <div className="w-3 h-3 rounded-full bg-red-400" />
                                <div className="w-3 h-3 rounded-full bg-yellow-400" />
                                <div className="w-3 h-3 rounded-full bg-green-400" />
                            </div>
                            <div className="flex-1 text-center text-xs text-gray-400 font-mono">nexstep.app/dashboard</div>
                        </div>

                        {/* Mock Dashboard Content */}
                        <div className="flex h-full bg-gray-50">
                            {/* Sidebar Mock */}
                            <div className="w-48 border-r border-gray-200 bg-white p-4 hidden sm:block">
                                <div className="space-y-3">
                                    <div className="h-2 w-20 bg-gray-200 rounded animate-pulse" />
                                    <div className="h-8 w-full bg-primary-50 rounded-md" />
                                    <div className="h-8 w-full bg-gray-100 rounded-md" />
                                    <div className="h-8 w-full bg-gray-100 rounded-md" />
                                </div>
                            </div>
                            {/* Main Area Mock */}
                            <div className="flex-1 p-6">
                                <div className="flex justify-between mb-6">
                                    <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
                                    <div className="h-8 w-24 bg-primary-600 rounded opacity-20" />
                                </div>
                                <div className="grid grid-cols-3 gap-4 mb-6">
                                    <div className="h-24 bg-white rounded-lg border border-gray-200 p-4" />
                                    <div className="h-24 bg-white rounded-lg border border-gray-200 p-4" />
                                    <div className="h-24 bg-white rounded-lg border border-gray-200 p-4" />
                                </div>
                                <div className="h-64 bg-white rounded-lg border border-gray-200 p-4" />
                            </div>
                        </div>
                    </div>
                </motion.div>
            </div>

            {/* Background elements */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
                <div className="absolute top-[-10%] right-[-5%] w-[500px] h-[500px] bg-primary-100/30 rounded-full blur-[100px]" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-blue-50/50 rounded-full blur-[120px]" />
            </div>
        </section>
    );
}
