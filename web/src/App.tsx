import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import MainLayout from './components/layout/MainLayout';
import Home from './pages/Home';
import Writer from './pages/Writer';
import Reader from './pages/Reader';
import WorkflowMonitor from './pages/WorkflowMonitor';
import ResourceMonitor from './pages/ResourceMonitor';
import PromptManager from './pages/PromptManager';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  try {
    return (
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Routes>
              <Route element={<MainLayout />}>
                <Route path="/" element={<Home />} />
                <Route path="/writer" element={<Writer />} />
                <Route path="/reader" element={<Reader />} />
                <Route path="/controller" element={<Navigate to="/workflow" replace />} />
                <Route path="/workflow" element={<WorkflowMonitor />} />
                <Route path="/resources" element={<ResourceMonitor />} />
                <Route path="/prompts" element={<PromptManager />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </QueryClientProvider>
      </ErrorBoundary>
    );
  } catch (error) {
    console.error('App render error:', error);
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-red-50">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-900">应用启动错误</h1>
          <p className="text-red-600 mt-2">{String(error)}</p>
        </div>
      </div>
    );
  }
}

export default App;
