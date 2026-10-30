import { useState } from 'react';
import { Header } from './components/Header';
import { UploadForm } from './components/UploadForm';
import { Dashboard } from './components/Dashboard';
import type { CsvProcessingResponse } from './types';
import './index.css';

function App() {
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<CsvProcessingResponse | null>(null);
  const [globalError, setGlobalError] = useState<string>('');

  const handleUpload = async (file: File, agentId: string) => {
    setLoading(true);
    setGlobalError('');
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('agent_id', agentId);

    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

    try {
      const response = await fetch(`${baseUrl}/api/v1/leads/upload-csv`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setResult(data as CsvProcessingResponse);
      } else {
        setGlobalError(data.detail || 'Failed to validate CSV due to server error.');
      }
    } catch (err) {
      console.error(err);
      setGlobalError('Error connecting to the validation server. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setGlobalError('');
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col font-sans selection:bg-accent/30">
      <Header />

      <main className="flex-1 flex flex-col py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto w-full flex-1 flex flex-col">

          {!result ? (
            <div className="flex-1 flex flex-col items-center justify-center space-y-12 max-w-3xl mx-auto w-full animate-in fade-in slide-in-from-bottom-8 duration-700">
              <div className="text-center space-y-4">
                <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white">
                  Validate Your Leads
                </h1>
                <p className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto">
                  Upload your CSV file to instantly clean, parse, and validate lead data before import.
                </p>
              </div>

              <UploadForm onUpload={handleUpload} loading={loading} />

              {globalError && (
                <div className="w-full max-w-2xl p-4 bg-error/10 border border-error/20 rounded-lg text-error text-center shadow-lg shadow-error/5">
                  <p className="font-medium">{globalError}</p>
                </div>
              )}
            </div>
          ) : (
            <Dashboard data={result} onReset={handleReset} />
          )}

        </div>
      </main>
    </div>
  );
}

export default App;
