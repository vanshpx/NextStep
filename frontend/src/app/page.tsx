import HeroSection from "@/components/landing/HeroSection";
import FeatureCards from "@/components/landing/FeatureCards";
import ProductPreview from "@/components/landing/ProductPreview";
import FinalCTA from "@/components/landing/FinalCTA";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-white text-gray-900 selection:bg-primary-100 overflow-x-hidden">
      <HeroSection />
      <FeatureCards />
      <ProductPreview />
      <FinalCTA />
    </main>
  );
}
