// Phase 11 Task 4 — Institutional Report Export Dropdown
// Replaces basic PDF export with full export menu

import { useState, useRef, useEffect } from 'react';
import { Printer, FileText, Globe, PieChart, Download, Share2, Mail, ChevronDown, X } from 'lucide-react';
import { cn } from '@/lib/utils';

type ReportType = 'morning-briefing' | 'risk-summary' | 'regime-dive' | 'portfolio-review' | 'global-macro';

interface ExportOption {
  id: ReportType | 'csv' | 'share' | 'email';
  label: string;
  icon: React.ReactNode;
  description?: string;
  separator?: boolean;
}

const exportOptions: ExportOption[] = [
  { id: 'morning-briefing', label: 'Morning Briefing', icon: <FileText className="w-4 h-4" />, description: 'Full 4-page institutional report' },
  { id: 'risk-summary', label: 'Risk Summary', icon: <Printer className="w-4 h-4" />, description: '1-page risk indicators + signals' },
  { id: 'global-macro', label: 'Global Macro Report', icon: <Globe className="w-4 h-4" />, description: 'Country matrix + CB divergence' },
  { id: 'portfolio-review', label: 'Portfolio Review', icon: <PieChart className="w-4 h-4" />, description: 'Portfolio analytics + stress tests' },
  { id: 'csv', label: 'Raw Data (CSV)', icon: <Download className="w-4 h-4" />, description: 'Export all visible data', separator: true },
  { id: 'share', label: 'Share Link', icon: <Share2 className="w-4 h-4" />, description: 'Copy URL to clipboard' },
  { id: 'email', label: 'Email Report', icon: <Mail className="w-4 h-4" />, description: 'Open mailto with report' },
];

export function ExportDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [copied, setCopied] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleExportPDF = async (reportType: ReportType) => {
    setIsExporting(true);
    setIsOpen(false);

    try {
      // Fetch HTML report from API
      const response = await fetch(`/api/report/export?format=html&type=${reportType}`);
      if (!response.ok) {
        throw new Error('Failed to generate report');
      }

      const html = await response.text();

      // Open in new window and print
      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(html);
        printWindow.document.close();

        // Wait for load then print
        printWindow.onload = () => {
          setTimeout(() => {
            printWindow.print();
          }, 500);
        };
      }
    } catch (error) {
      console.error('Export failed:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportCSV = () => {
    setIsOpen(false);

    // Collect all visible data from the dashboard
    const csvData: Record<string, (string | number)[]> = {
      timestamp: [new Date().toISOString()],
    };

    // Try to extract data from the page
    document.querySelectorAll('[data-metric]').forEach((el) => {
      const key = el.getAttribute('data-metric');
      const value = el.textContent?.trim() || '';
      if (key && value) {
        csvData[key] = [value];
      }
    });

    // Create CSV content
    const headers = Object.keys(csvData);
    const rows = Object.values(csvData);
    const maxRows = Math.max(...rows.map(r => r.length), 1);

    let csv = headers.join(',') + '\n';
    for (let i = 0; i < maxRows; i++) {
      const row = headers.map(h => {
        const val = csvData[h]?.[i] || '';
        // Escape commas and quotes
        if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
          return `"${val.replace(/"/g, '""')}"`;
        }
        return val;
      });
      csv += row.join(',') + '\n';
    }

    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `macro-research-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const handleShare = async () => {
    setIsOpen(false);

    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleEmail = () => {
    setIsOpen(false);

    const subject = encodeURIComponent('Macro Research Platform Report');
    const body = encodeURIComponent(
      `View the latest macro research report:\n\n${window.location.href}\n\n---\nMacro Research Platform`
    );
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  };

  const handleSelect = (option: ExportOption) => {
    if (option.id === 'csv') {
      handleExportCSV();
    } else if (option.id === 'share') {
      handleShare();
    } else if (option.id === 'email') {
      handleEmail();
    } else {
      handleExportPDF(option.id as ReportType);
    }
  };

  // Report type labels for future use
  // const reportTypeLabels: Record<ReportType, string> = {
  //   'morning-briefing': 'Morning Briefing',
  //   'risk-summary': 'Risk Summary',
  //   'regime-dive': 'Regime Deep Dive',
  //   'portfolio-review': 'Portfolio Review',
  //   'global-macro': 'Global Macro',
  // };

  return (
    <div ref={dropdownRef} className="relative">
      {/* Main Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isExporting}
        className={cn(
          'flex items-center gap-2 px-3 py-1.5 border rounded text-xs font-medium transition-colors',
          isOpen
            ? 'bg-accent text-bg border-accent'
            : 'bg-surface-2 text-text-secondary border-border-subtle hover:bg-surface-3 hover:text-text-primary'
        )}
      >
        {isExporting ? (
          <>
            <FileText className="w-3 h-3 animate-pulse" />
            <span>Generating...</span>
          </>
        ) : (
          <>
            <Printer className="w-3 h-3" />
            <span>Export</span>
            <ChevronDown className={cn('w-3 h-3 transition-transform', isOpen && 'rotate-180')} />
          </>
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-1 w-72 bg-bg border border-border shadow-lg z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
            <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
              Export Options
            </span>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-surface-2 rounded"
            >
              <X className="w-3 h-3 text-text-tertiary" />
            </button>
          </div>

          {/* PDF Reports Section */}
          <div className="px-3 py-2 border-b border-border-subtle">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">PDF Reports</span>
          </div>

          {/* Options */}
          <div className="py-1">
            {exportOptions.map((option) => (
              <div key={option.id}>
                {option.separator && (
                  <div className="my-1 border-t border-border-subtle" />
                )}
                <button
                  onClick={() => handleSelect(option)}
                  className="w-full flex items-start gap-3 px-3 py-2 hover:bg-surface-1 transition-colors text-left"
                >
                  <span className="mt-0.5 text-text-secondary">{option.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-text-primary">{option.label}</div>
                    {option.description && (
                      <div className="text-2xs text-text-tertiary mt-0.5 truncate">
                        {option.description}
                      </div>
                    )}
                  </div>
                </button>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="px-3 py-2 border-t border-border-subtle bg-surface-1">
            <div className="flex items-center justify-between text-2xs text-text-tertiary">
              <span>Format: A4 Landscape</span>
              {copied && <span className="text-green">Link copied!</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Legacy export button for backward compatibility
export function PDFExportButton() {
  return <ExportDropdown />;
}

// Hook for sections to know if they're being printed
export function useIsPrinting(): boolean {
  const [isPrinting, setIsPrinting] = useState(false);

  useEffect(() => {
    const handleBeforePrint = () => setIsPrinting(true);
    const handleAfterPrint = () => setIsPrinting(false);

    window.addEventListener('beforeprint', handleBeforePrint);
    window.addEventListener('afterprint', handleAfterPrint);

    return () => {
      window.removeEventListener('beforeprint', handleBeforePrint);
      window.removeEventListener('afterprint', handleAfterPrint);
    };
  }, []);

  return isPrinting;
}
