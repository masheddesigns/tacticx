import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from './components/layout/Navbar';
import { Footer } from './components/layout/Footer';
import { ApplicationErrorBoundary } from './components/common/ApplicationErrorBoundary';
import { DashboardPage } from './pages/DashboardPage';
import { MatchExplorerPage } from './pages/MatchExplorerPage';
import { MatchIntelligencePage } from './pages/MatchIntelligencePage';
import { SystemStatusPage } from './pages/SystemStatusPage';
import { MonitoringPage } from './pages/MonitoringPage';
import { ResearchPage } from './pages/ResearchPage';
import { ValidationPage } from './pages/ValidationPage';
import { EvidencePage } from './pages/EvidencePage';
import { ShadowPage } from './pages/ShadowPage';
import { ModelGovernancePage } from './pages/ModelGovernancePage';
import { OperationsPage } from './pages/OperationsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export const App: React.FC = () => {
  return (
    <ApplicationErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <div className="flex flex-col min-h-screen bg-[#090d16] text-slate-100 font-sans selection:bg-emerald-500/20 selection:text-emerald-300">
          <Navbar />
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/matches" element={<MatchExplorerPage />} />
              <Route path="/matches/:matchId" element={<MatchIntelligencePage />} />
              <Route path="/system" element={<SystemStatusPage />} />
              <Route path="/monitoring" element={<MonitoringPage />} />
              <Route path="/research" element={<ResearchPage />} />
              <Route path="/validation" element={<ValidationPage />} />
              <Route path="/evidence" element={<EvidencePage />} />
              <Route path="/shadow" element={<ShadowPage />} />
              <Route path="/model-governance" element={<ModelGovernancePage />} />
              <Route path="/operations" element={<OperationsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <Footer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
    </ApplicationErrorBoundary>
  );
};

export default App;
