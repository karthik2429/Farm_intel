import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { Toaster as Sonner } from '@/components/ui/sonner';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { ThemeProvider } from '@/components/ThemeProvider';
import { SetupStatusPanel } from '@/components/SetupStatusPanel';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui-kit/core';
import { readCachedProfile } from '@/lib/profile';

const LoginPage = React.lazy(() => import('./pages/LoginPage'));
const ProfileSetupPage = React.lazy(() => import('./pages/ProfileSetupPage'));
const HomeDashboard = React.lazy(() => import('./pages/HomeDashboard'));
const CropRecommendationsPage = React.lazy(() => import('./pages/CropRecommendationsPage'));
const CropDetailPage = React.lazy(() => import('./pages/CropDetailPage'));
const MarketPricesPage = React.lazy(() => import('./pages/MarketPricesPage'));
const PricePredictionPage = React.lazy(() => import('./pages/PricePredictionPage'));
const CropRotationPage = React.lazy(() => import('./pages/CropRotationPage'));
const FertilizerRecommendationPage = React.lazy(() => import('./pages/FertilizerRecommendationPage'));
const ChatPage = React.lazy(() => import('./pages/ChatPage'));
const FarmerProfilePage = React.lazy(() => import('./pages/FarmerProfilePage'));
const DesignGallery = React.lazy(() => import('./pages/DesignGallery'));
const NotFound = React.lazy(() => import('./pages/NotFound'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 60_000 },
  },
});

function RouteFallback() {
  return (
    <div className="mx-auto w-full max-w-content space-y-3 px-4 py-6">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-20 w-full" />
    </div>
  );
}

/**
 * First-run gate.
 *
 * Without a saved profile every price screen falls back to nationwide markets,
 * which is misleading. Send the farmer to onboarding once. The
 * `agrosmart.onboarding_seen` flag is written the moment onboarding opens, so
 * choosing "Skip" is honoured and can never cause a redirect loop.
 */
function RequireOnboarding() {
  const seen = localStorage.getItem('agrosmart.onboarding_seen') === '1';
  const complete = Boolean(readCachedProfile()?.onboarding_complete);
  if (!seen && !complete) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <AuthProvider>
        <LanguageProvider>
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <BrowserRouter>
              <ErrorBoundary>
              <React.Suspense fallback={<RouteFallback />}>
                <Routes>
                  <Route path="/" element={<LoginPage />} />
                  <Route path="/onboarding" element={<ProfileSetupPage />} />
                  <Route path="/setup" element={<Navigate to="/onboarding" replace />} />

                  {/* Everything below needs a location to be useful. */}
                  <Route element={<RequireOnboarding />}>
                    <Route path="/home" element={<HomeDashboard />} />
                    <Route path="/market" element={<MarketPricesPage />} />
                    <Route path="/predict" element={<PricePredictionPage />} />
                    <Route path="/price-prediction" element={<Navigate to="/predict" replace />} />
                    <Route path="/crops" element={<CropRecommendationsPage />} />
                    <Route path="/crop-recommendations" element={<Navigate to="/crops" replace />} />
                    <Route path="/crop-detail" element={<CropDetailPage />} />
                    <Route path="/rotation" element={<CropRotationPage />} />
                    <Route path="/crop-rotation" element={<Navigate to="/rotation" replace />} />
                    <Route path="/fertilizer" element={<FertilizerRecommendationPage />} />
                    <Route path="/chat" element={<ChatPage />} />
                    <Route path="/ai-chat" element={<Navigate to="/chat" replace />} />
                    <Route path="/profile" element={<FarmerProfilePage />} />
                    <Route path="/marketplace" element={<Navigate to="/market" replace />} />
                  </Route>

                  <Route path="/design" element={<DesignGallery />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </React.Suspense>
              </ErrorBoundary>
              <SetupStatusPanel />
            </BrowserRouter>
          </TooltipProvider>
        </LanguageProvider>
      </AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
