import React, { useState, useRef } from 'react';
import { UploadCloud, FileType, AlertCircle, Loader2 } from 'lucide-react';

interface UploadFormProps {
  onUpload: (file: File, agentId: string) => Promise<void>;
  loading: boolean;
}

export function UploadForm({ onUpload, loading }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [agentId, setAgentId] = useState<string>('');
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.name.endsWith('.csv')) {
        setFile(droppedFile);
        setError('');
      } else {
        setError('Please upload a valid .csv file');
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.name.endsWith('.csv')) {
        setFile(selectedFile);
        setError('');
      } else {
        setError('Please upload a valid .csv file');
      }
    }
  };

  const onButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file to upload');
      return;
    }
    if (!agentId.trim()) {
      setError('Agent ID is required');
      return;
    }
    setError('');
    onUpload(file, agentId);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto space-y-6">
      <div className="space-y-2">
        <label htmlFor="agentId" className="block text-sm font-medium text-gray-300">
          Agent ID
        </label>
        <input
          type="text"
          id="agentId"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          placeholder="e.g. agt_12345"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
          disabled={loading}
        />
      </div>

      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-300">
          Lead Data (CSV)
        </label>
        <div
          className={`relative border-2 border-dashed rounded-xl p-8 transition-all ${
            dragActive
              ? 'border-accent bg-accent/10'
              : 'border-gray-700 bg-gray-800/50 hover:bg-gray-800'
          } ${file ? 'border-success/50 bg-success/5' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleChange}
            className="hidden"
            disabled={loading}
          />

          <div className="flex flex-col items-center justify-center text-center space-y-4">
            {file ? (
              <>
                <div className="p-3 bg-success/20 rounded-full text-success">
                  <FileType size={32} />
                </div>
                <div>
                  <p className="text-white font-medium">{file.name}</p>
                  <p className="text-sm text-gray-400 mt-1">{formatFileSize(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  className="text-sm text-red-400 hover:text-red-300 transition-colors"
                  disabled={loading}
                >
                  Remove file
                </button>
              </>
            ) : (
              <>
                <div className="p-4 bg-gray-800 rounded-full text-gray-400">
                  <UploadCloud size={40} />
                </div>
                <div>
                  <p className="text-lg font-medium text-gray-200">
                    Drag & drop your CSV here
                  </p>
                  <p className="text-sm text-gray-400 mt-2">
                    or{' '}
                    <button
                      type="button"
                      onClick={onButtonClick}
                      className="text-accent hover:text-accent-hover font-medium transition-colors"
                      disabled={loading}
                    >
                      browse your files
                    </button>
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center space-x-2 text-error text-sm p-3 bg-error/10 rounded-lg border border-error/20">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !file || !agentId.trim()}
        className={`w-full py-4 rounded-lg font-medium text-lg flex items-center justify-center space-x-2 transition-all ${
          loading || !file || !agentId.trim()
            ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
            : 'bg-accent hover:bg-accent-hover text-white shadow-lg shadow-accent/20'
        }`}
      >
        {loading ? (
          <>
            <Loader2 className="animate-spin" size={24} />
            <span>Validating Leads...</span>
          </>
        ) : (
          <span>Validate Leads</span>
        )}
      </button>
    </form>
  );
}
