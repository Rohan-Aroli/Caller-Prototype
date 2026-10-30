import { useState } from 'react';
import type { CsvProcessingResponse } from '../types';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { CheckCircle2, XCircle, Users, Download, ArrowLeft, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import Papa from 'papaparse';

interface DashboardProps {
  data: CsvProcessingResponse;
  onReset: () => void;
}

export function Dashboard({ data, onReset }: DashboardProps) {
  const [activeTab, setActiveTab] = useState<'accepted' | 'rejected'>('accepted');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const total = data.total_rows || 1; // Prevent division by zero
  const acceptPercent = Math.round((data.accepted_count / total) * 100);
  const rejectPercent = Math.round((data.rejected_count / total) * 100);

  const chartData = [
    { name: 'Accepted', value: data.accepted_count, color: '#10b981' },
    { name: 'Rejected', value: data.rejected_count, color: '#ef4444' },
  ].filter(item => item.value > 0);

  const handleExportRejected = () => {
    if (data.rejected_rows.length === 0) return;
    const exportData = data.rejected_rows.map(row => ({
      'Row Number': row.row_number,
      'Errors': row.errors.join(' | ')
    }));
    const csv = Papa.unparse(exportData);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `rejected_rows_agent_${data.agent_id}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredAccepted = data.accepted_leads.filter(lead => {
    const searchLower = searchTerm.toLowerCase();
    const nameMatch = (lead.name || '').toLowerCase().includes(searchLower);
    const phoneMatch = (lead.phone || '').toLowerCase().includes(searchLower);

    let extraMatch = false;
    if (lead.extra_fields) {
        extraMatch = Object.values(lead.extra_fields).some(val =>
            String(val).toLowerCase().includes(searchLower)
        );
    }
    return nameMatch || phoneMatch || extraMatch;
  });

  const filteredRejected = data.rejected_rows.filter(row =>
    row.row_number.toString().includes(searchTerm) ||
    row.errors.some(err => err.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const currentData = activeTab === 'accepted' ? filteredAccepted : filteredRejected;
  const totalPages = Math.max(1, Math.ceil(currentData.length / itemsPerPage));
  const paginatedData = currentData.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Validation Results</h2>
          <p className="text-gray-400 mt-1">Agent ID: <span className="text-gray-200 font-medium">{data.agent_id}</span></p>
        </div>
        <button
          onClick={onReset}
          className="flex items-center space-x-2 text-gray-400 hover:text-white transition-colors bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg border border-gray-700"
        >
          <ArrowLeft size={16} />
          <span>Upload Another</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 flex flex-col justify-center">
          <div className="flex items-center space-x-3 text-gray-400 mb-2">
            <Users size={20} />
            <h3 className="font-medium">Total Rows</h3>
          </div>
          <p className="text-4xl font-bold text-white">{data.total_rows}</p>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 flex flex-col justify-center relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-success/5 rounded-full -mr-16 -mt-16 blur-2xl"></div>
          <div className="flex items-center space-x-3 text-gray-400 mb-2 relative z-10">
            <CheckCircle2 size={20} className="text-success" />
            <h3 className="font-medium">Accepted</h3>
          </div>
          <div className="flex items-end space-x-3 relative z-10">
            <p className="text-4xl font-bold text-white">{data.accepted_count}</p>
            <p className="text-success font-medium mb-1">{acceptPercent}%</p>
          </div>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 flex flex-col justify-center relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-error/5 rounded-full -mr-16 -mt-16 blur-2xl"></div>
          <div className="flex items-center space-x-3 text-gray-400 mb-2 relative z-10">
            <XCircle size={20} className="text-error" />
            <h3 className="font-medium">Rejected</h3>
          </div>
          <div className="flex items-end space-x-3 relative z-10">
            <p className="text-4xl font-bold text-white">{data.rejected_count}</p>
            <p className="text-error font-medium mb-1">{rejectPercent}%</p>
          </div>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 h-32 md:h-auto flex items-center justify-center">
          {data.total_rows > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={30}
                  outerRadius={45}
                  paddingAngle={5}
                  dataKey="value"
                  stroke="none"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1d24', borderColor: '#262a33', borderRadius: '8px', color: 'white' }}
                  itemStyle={{ color: 'white' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-sm">No data to chart</p>
          )}
        </div>
      </div>

      <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
        <div className="flex flex-col sm:flex-row border-b border-gray-700 p-4 gap-4 justify-between items-center bg-gray-900/30">
          <div className="flex space-x-2 w-full sm:w-auto">
            <button
              onClick={() => { setActiveTab('accepted'); setCurrentPage(1); setSearchTerm(''); }}
              className={`flex-1 sm:flex-none px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'accepted'
                  ? 'bg-success/20 text-success border border-success/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
              }`}
            >
              Accepted ({data.accepted_count})
            </button>
            <button
              onClick={() => { setActiveTab('rejected'); setCurrentPage(1); setSearchTerm(''); }}
              className={`flex-1 sm:flex-none px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'rejected'
                  ? 'bg-error/20 text-error border border-error/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
              }`}
            >
              Rejected ({data.rejected_count})
            </button>
          </div>

          <div className="flex w-full sm:w-auto space-x-3">
            <div className="relative w-full sm:w-64">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500">
                <Search size={16} />
              </div>
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-accent focus:border-accent"
              />
            </div>

            {activeTab === 'rejected' && data.rejected_count > 0 && (
              <button
                onClick={handleExportRejected}
                title="Export Rejected Rows"
                className="flex items-center justify-center p-2 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg text-white transition-colors whitespace-nowrap"
              >
                <Download size={18} />
                <span className="ml-2 text-sm hidden sm:inline">Export</span>
              </button>
            )}
          </div>
        </div>

        <div className="overflow-x-auto min-h-[300px]">
          {paginatedData.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-gray-500">
              <p>No results found.</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="bg-gray-900/50 text-gray-400 text-xs uppercase font-semibold">
                {activeTab === 'accepted' ? (
                  <tr>
                    <th className="px-6 py-4 border-b border-gray-700">Name</th>
                    <th className="px-6 py-4 border-b border-gray-700">Phone</th>
                    <th className="px-6 py-4 border-b border-gray-700">Other Details</th>
                  </tr>
                ) : (
                  <tr>
                    <th className="px-6 py-4 border-b border-gray-700 w-24">Row</th>
                    <th className="px-6 py-4 border-b border-gray-700">Rejection Reasons</th>
                  </tr>
                )}
              </thead>
              <tbody className="text-sm divide-y divide-gray-700/50">
                {activeTab === 'accepted' ? (
                  (paginatedData as any[]).map((lead, idx) => (
                    <tr key={idx} className="hover:bg-gray-700/30 transition-colors">
                      <td className="px-6 py-4 text-gray-200 font-medium">{lead.name || '-'}</td>
                      <td className="px-6 py-4 text-gray-300">{lead.phone || '-'}</td>
                      <td className="px-6 py-4 text-gray-400">
                        {Object.entries(lead.extra_fields || {})
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(', ') || '-'}
                      </td>
                    </tr>
                  ))
                ) : (
                  (paginatedData as any[]).map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-700/30 transition-colors">
                      <td className="px-6 py-4 text-gray-400 font-mono">#{row.row_number}</td>
                      <td className="px-6 py-4">
                        <ul className="list-disc list-inside text-error space-y-1">
                          {row.errors.map((err: string, i: number) => (
                            <li key={i}>{err}</li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-700 bg-gray-900/30">
            <p className="text-sm text-gray-400">
              Showing <span className="font-medium text-gray-200">{(currentPage - 1) * itemsPerPage + 1}</span> to <span className="font-medium text-gray-200">{Math.min(currentPage * itemsPerPage, currentData.length)}</span> of <span className="font-medium text-gray-200">{currentData.length}</span> results
            </p>
            <div className="flex space-x-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-1 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={20} />
              </button>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                className="p-1 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={20} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
