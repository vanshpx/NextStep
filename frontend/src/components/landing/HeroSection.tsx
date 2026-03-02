"use client";

import { Button } from "@/components/ui/Button";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";


export default function HeroSection() {
    const ref = useRef(null);
    const { scrollY } = useScroll();
    const y1 = useTransform(scrollY, [0, 500], [0, 200]);

    return (
        <section ref={ref} className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden pt-48 pb-20">
            {/* Background is now handled globally in page.tsx */}

            {/* Navigation (simplified for hero) */}
            <nav className="fixed top-0 inset-x-0 z-50 h-20 flex items-center justify-between px-6 lg:px-12 bg-white/30 backdrop-blur-[5px] border-b border-gray-100">
                <div className="flex items-center gap-2">
                    <img src="/pinwheel.png" alt="NexStep Logo" className="w-8 h-8 object-contain" />
                    <span className="text-2xl font-bold text-gray-900 tracking-normal">NexStep</span>
                </div>

                <div className="flex items-center gap-6">
                    <div className="hidden md:flex items-center gap-6 text-lg font-medium text-black-800">
                        <a href="#features" className="hover:text-primary-600 transition-colors font-semibold">Features</a>
                    </div>
                    <div className="hidden md:flex items-center gap-6 text-lg font-medium text-black-800">
                        <a href="/dashboard" className="hover:text-primary-600 transition-colors font-semibold">Login</a>
                    </div>
                    {/* <Link href="/dashboard">
                        <Button variant="ghost" className="text-gray-800 hover:text-primary-600 font-semibold drop-shadow-sm bg-white/50 hover:bg-white/80">Log In</Button>
                    </Link> */}
                </div>
            </nav>

            {/* Repositioned Hero Text Container for Sky Placement */}
            <div className="absolute top-[30%] left-6 md:left-24 max-w-2xl z-20">
                <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="space-y-6"
                >
                    <h1 className="text-5xl md:text-7xl font-bold text-white leading-[1.1] drop-shadow-lg">
                        Smart itinerary management
                        <br />
                        for modern agents.
                    </h1>

                    <p className="text-xl text-white/90 font-medium max-w-xl drop-shadow-md">
                        NexStep brings clarity to travel planning. Create professional itineraries and manage live disruptions in one workspace.
                    </p>

                    <div className="pt-3">
                        <Link href="/dashboard">
                            <Button variant="ghost" size="lg" className="bg-transparent hover:bg-black text-black hover:text-white rounded-full px-8 h-14 text-lg border-2 border-black hover:border-white transition-all duration-600 hover:scale-100">
                                Start Making Itinerary
                                <ArrowRight className="ml-2 w-5 h-5" />
                            </Button>
                        </Link>
                    </div>
                </motion.div>
            </div>

            {/* Decorative glows adjusted for the image background */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none mix-blend-overlay">
                <div className="absolute top-[-10%] right-[-5%] w-[500px] h-[500px] bg-primary-300/40 rounded-full blur-[100px]" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-teal-200/50 rounded-full blur-[120px]" />
            </div>
        </section>
    );
}
