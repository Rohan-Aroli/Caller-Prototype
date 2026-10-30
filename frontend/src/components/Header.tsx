import { PhoneCall } from 'lucide-react';

export function Header() {
  return (
    <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center space-x-3">
            <div className="bg-accent/10 p-2 rounded-lg text-accent">
              <PhoneCall size={24} />
            </div>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
              Caller-AI
            </span>
          </div>
          <div className="text-sm text-gray-400 font-medium px-3 py-1 rounded-full bg-gray-800 border border-gray-700">
            Lead Validation Portal
          </div>
        </div>
      </div>
    </header>
  );
}
