import HeroSection from "@/components/landing/HeroSection";
import FeatureCards from "@/components/landing/FeatureCards";
import FinalCTA from "@/components/landing/FinalCTA";

export default function Home() {
  return (
    <main className="relative min-h-screen flex flex-col text-gray-900 selection:bg-primary-100 overflow-x-hidden">
      {/* Global Background Image - Scrollable & Shifted Upwards */}
      <div className="absolute top-[-5%] left-0 w-full h-[105%] -z-20 pointer-events-none">
        <img
          src="/jodhpur1.jpg"
          alt="Jodhpur Background"
          className="w-full h-full object-cover"
        />
      </div>

      <div className="relative z-10 w-full">
        <HeroSection />
        <FeatureCards />
        <FinalCTA />
      </div>
    </main>
  );
}
