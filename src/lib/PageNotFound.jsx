import React from 'react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import { Button } from '@/components/ui/button';
import { ShieldOff, Home, ArrowLeft } from 'lucide-react';

export default function PageNotFound() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="w-20 h-20 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <ShieldOff className="w-10 h-10 text-slate-400" />
        </div>
        
        <h1 className="text-6xl font-bold text-slate-900 mb-2">404</h1>
        <h2 className="text-xl font-semibold text-slate-700 mb-4">Page Not Found</h2>
        
        <p className="text-slate-500 mb-8">
          The page you're looking for doesn't exist or has been moved. 
          Please check the URL or navigate back to the dashboard.
        </p>
        
        <div className="flex items-center justify-center gap-3">
          <Button 
            variant="outline" 
            onClick={() => window.history.back()}
            className="gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </Button>
          
          <Link to={createPageUrl('Dashboard')}>
            <Button className="bg-emerald-600 hover:bg-emerald-700 gap-2">
              <Home className="w-4 h-4" />
              Dashboard
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}