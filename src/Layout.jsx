import React, { useState } from 'react';
import { base44 } from '@/api/base44Client';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import { cn } from '@/lib/utils';
import { Toaster } from '@/components/ui/toaster';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { FileBarChart, Download, Loader2 } from 'lucide-react';

export default function Layout({ children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [reportConfig, setReportConfig] = useState({
    type: 'Executive Summary',
    format: 'PDF',
    frameworks: ['NCA ECC', 'ISO 27001', 'NIST 800-53']
  });

  const handleGenerateReport = () => {
    setShowReportDialog(true);
  };

  const handleConfirmReport = async () => {
    setReportGenerating(true);
    
    try {
      // Get latest analyzed policy
      const { data: policies } = await base44.entities.Policy.filter({ status: 'analyzed' });
      
      if (policies && policies.length > 0) {
        const latestPolicy = policies[0];
        
        const result = await base44.functions.invoke('generate_report', {
          policy_id: latestPolicy.id,
          report_type: reportConfig.type,
          format: reportConfig.format,
          frameworks_included: reportConfig.frameworks,
        });

        if (result.success) {
          // Download the report
          if (result.report?.download_url) {
            window.open(result.report.download_url, '_blank');
          }
        }
      }
    } catch (error) {
      console.error('Report generation failed:', error);
    }
    
    setReportGenerating(false);
    setShowReportDialog(false);
  };

  const toggleFramework = (framework) => {
    setReportConfig(prev => ({
      ...prev,
      frameworks: prev.frameworks.includes(framework)
        ? prev.frameworks.filter(f => f !== framework)
        : [...prev.frameworks, framework]
    }));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <style>{`
        :root {
          --color-primary: #10b981;
          --color-primary-dark: #059669;
          --color-secondary: #0d9488;
          --color-background: #f8fafc;
          --color-surface: #ffffff;
          --color-text-primary: #0f172a;
          --color-text-secondary: #64748b;
          --color-border: #e2e8f0;
        }
        
        * {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        .scrollbar-thin::-webkit-scrollbar {
          width: 6px;
        }
        
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 3px;
        }
        
        .scrollbar-thin::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>
      
      <Sidebar collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />
      
      <div className={cn(
        "transition-all duration-300",
        sidebarCollapsed ? "ml-20" : "ml-64"
      )}>
        <Topbar onGenerateReport={handleGenerateReport} />
        <main className="min-h-[calc(100vh-4rem)]">
          {children}
        </main>
      </div>
      
      <Toaster />

      {/* Report Generation Dialog */}
      <Dialog open={showReportDialog} onOpenChange={setShowReportDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileBarChart className="w-5 h-5 text-emerald-600" />
              Generate Compliance Report
            </DialogTitle>
            <DialogDescription>
              Configure your report settings and generate a comprehensive compliance report.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Report Type</Label>
              <Select 
                value={reportConfig.type} 
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, type: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Executive Summary">Executive Summary</SelectItem>
                  <SelectItem value="Detailed Analysis">Detailed Analysis</SelectItem>
                  <SelectItem value="Gap Report">Gap Report</SelectItem>
                  <SelectItem value="Compliance Certificate">Compliance Certificate</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Format</Label>
              <Select 
                value={reportConfig.format} 
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, format: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PDF">PDF Document</SelectItem>
                  <SelectItem value="Excel">Excel Spreadsheet</SelectItem>
                  <SelectItem value="CSV">CSV Export</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Include Frameworks</Label>
              <div className="space-y-2">
                {['NCA ECC', 'ISO 27001', 'NIST 800-53'].map(framework => (
                  <div key={framework} className="flex items-center gap-2">
                    <Checkbox
                      id={framework}
                      checked={reportConfig.frameworks.includes(framework)}
                      onCheckedChange={() => toggleFramework(framework)}
                    />
                    <Label htmlFor={framework} className="font-normal cursor-pointer">
                      {framework}
                    </Label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowReportDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleConfirmReport}
              disabled={reportGenerating || reportConfig.frameworks.length === 0}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {reportGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Generate Report
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}