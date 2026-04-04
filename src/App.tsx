import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { AuthProvider } from "@/contexts/AuthContext";
import OnboardingPage from "./pages/OnboardingPage";
import ProfileSetupPage from "./pages/ProfileSetupPage";
import HomeDashboard from "./pages/HomeDashboard";
import CropRecommendationsPage from "./pages/CropRecommendationsPage";
import CropDetailPage from "./pages/CropDetailPage";
import MarketPricesPage from "./pages/MarketPricesPage";
import PricePredictionPage from "./pages/PricePredictionPage";
import CropRotationPage from "./pages/CropRotationPage";
import AIChatPage from "./pages/AIChatPage";
import FarmerProfilePage from "./pages/FarmerProfilePage";
import MarketplacePage from "./pages/MarketplacePage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <LanguageProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <div className="max-w-lg mx-auto min-h-screen">
              <Routes>
                <Route path="/" element={<OnboardingPage />} />
                <Route path="/setup" element={<ProfileSetupPage />} />
                <Route path="/home" element={<HomeDashboard />} />
                <Route path="/crop-recommendations" element={<CropRecommendationsPage />} />
                <Route path="/crop-detail" element={<CropDetailPage />} />
                <Route path="/market" element={<MarketPricesPage />} />
                <Route path="/price-prediction" element={<PricePredictionPage />} />
                <Route path="/crop-rotation" element={<CropRotationPage />} />
                <Route path="/crops" element={<CropRecommendationsPage />} />
                <Route path="/ai-chat" element={<AIChatPage />} />
                <Route path="/profile" element={<FarmerProfilePage />} />
                <Route path="/marketplace" element={<MarketplacePage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </div>
          </BrowserRouter>
        </TooltipProvider>
      </LanguageProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
