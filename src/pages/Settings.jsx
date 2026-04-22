import React, { useState, useEffect } from 'react';
import { api } from '@/api/apiClient';
import { useAuth } from '@/lib/AuthContext';
import { useTheme } from '@/lib/ThemeContext';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  User,
  Bell,
  Shield,
  Database,
  Palette,
  Globe,
  Save,
  Key,
  Mail,
  Phone,
  Loader2
} from 'lucide-react';

export default function Settings() {
  const { user: ctxUser, login } = useAuth();
  const { theme, setTheme } = useTheme();
  const [user, setUser] = useState(ctxUser || null);
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState({
    // Notifications
    emailNotifications: true,
    analysisComplete: true,
    gapAlerts: true,
    weeklyDigest: true,

    // Security
    twoFactorAuth: false,
    sessionTimeout: '30',

    // Compliance
    defaultFramework: 'all',
    autoAnalysis: false,
    confidenceThreshold: '0.6',

    // Display
    language: 'en',
    dateFormat: 'MM/dd/yyyy',
    theme,
  });

  const { toast } = useToast();

  useEffect(() => {
    let cancelled = false;
    const loadUser = async () => {
      try {
        const userData = await api.auth.me();
        if (cancelled) return;
        setUser(userData);
        const token = localStorage.getItem('token');
        if (token) login({ token, user: userData });
        if (userData?.settings) {
          setSettings(prev => ({ ...prev, ...userData.settings, theme: userData.settings.theme || prev.theme }));
        }
      } catch {
        // fall back to cached ctx user
      }
    };
    loadUser();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    setLoading(true);
    try {
      await api.auth.updateMe({ settings });
      // Commit theme only on explicit save so the UI doesn't preview on dropdown change.
      if (settings.theme && settings.theme !== theme) {
        setTheme(settings.theme);
      }
      toast({
        title: 'Settings Saved',
        description: 'Your preferences have been updated successfully.',
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to save settings. Please try again.',
        variant: 'destructive',
      });
    }
    setLoading(false);
  };

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || '';

  return (
    <PageContainer
      title="Settings"
      subtitle="Manage your account and application preferences"
      actions={
        <Button 
          onClick={handleSave}
          disabled={loading}
          className="bg-emerald-600 hover:bg-emerald-700"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <Save className="w-4 h-4 mr-2" />
          )}
          Save Changes
        </Button>
      }
    >
      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="bg-slate-100 dark:bg-slate-800">
          <TabsTrigger value="profile" className="gap-2">
            <User className="w-4 h-4" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="w-4 h-4" />
            Notifications
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="w-4 h-4" />
            Security
          </TabsTrigger>
          <TabsTrigger value="compliance" className="gap-2">
            <Database className="w-4 h-4" />
            Compliance
          </TabsTrigger>
          <TabsTrigger value="display" className="gap-2">
            <Palette className="w-4 h-4" />
            Display
          </TabsTrigger>
        </TabsList>

        {/* Profile Tab */}
        <TabsContent value="profile">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="w-5 h-5 text-emerald-600" />
                Profile Information
              </CardTitle>
              <CardDescription>
                Your account details on file
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label>Full Name</Label>
                  <Input
                    value={fullName}
                    disabled
                    className="bg-slate-50 dark:bg-slate-800"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400">Contact support to change your name</p>
                </div>

                <div className="space-y-2">
                  <Label>Email Address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      value={user?.email || ''}
                      disabled
                      className="pl-10 bg-slate-50 dark:bg-slate-800"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Phone</Label>
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input
                      value={user?.phone || ''}
                      disabled
                      className="pl-10 bg-slate-50 dark:bg-slate-800"
                      placeholder="Not provided"
                    />
                  </div>
                </div>
              </div>

              <Separator />

              <div>
                <Label className="text-base font-medium">Role</Label>
                <div className="flex items-center gap-2 mt-2">
                  <Badge className="bg-emerald-100 text-emerald-700 capitalize">
                    {user?.role || 'User'}
                  </Badge>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    Contact your administrator to change your role
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="w-5 h-5 text-emerald-600" />
                Notification Preferences
              </CardTitle>
              <CardDescription>
                Configure how and when you receive notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Email Notifications</Label>
                  <p className="text-sm text-slate-500">Receive notifications via email</p>
                </div>
                <Switch
                  checked={settings.emailNotifications}
                  onCheckedChange={(checked) => updateSetting('emailNotifications', checked)}
                />
              </div>

              <Separator />

              <div className="space-y-4">
                <Label className="text-base font-medium">Notification Types</Label>
                
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Analysis Complete</Label>
                    <p className="text-sm text-slate-500">When a compliance analysis finishes</p>
                  </div>
                  <Switch
                    checked={settings.analysisComplete}
                    onCheckedChange={(checked) => updateSetting('analysisComplete', checked)}
                    disabled={!settings.emailNotifications}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label>Gap Alerts</Label>
                    <p className="text-sm text-slate-500">When new critical gaps are identified</p>
                  </div>
                  <Switch
                    checked={settings.gapAlerts}
                    onCheckedChange={(checked) => updateSetting('gapAlerts', checked)}
                    disabled={!settings.emailNotifications}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label>Weekly Digest</Label>
                    <p className="text-sm text-slate-500">Summary of compliance status every week</p>
                  </div>
                  <Switch
                    checked={settings.weeklyDigest}
                    onCheckedChange={(checked) => updateSetting('weeklyDigest', checked)}
                    disabled={!settings.emailNotifications}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Security Tab */}
        <TabsContent value="security">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-emerald-600" />
                Security Settings
              </CardTitle>
              <CardDescription>
                Manage your account security and authentication
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Two-Factor Authentication</Label>
                  <p className="text-sm text-slate-500">Add an extra layer of security to your account</p>
                </div>
                <Switch
                  checked={settings.twoFactorAuth}
                  onCheckedChange={(checked) => updateSetting('twoFactorAuth', checked)}
                />
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Session Timeout (minutes)</Label>
                <Select 
                  value={settings.sessionTimeout} 
                  onValueChange={(value) => updateSetting('sessionTimeout', value)}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15 minutes</SelectItem>
                    <SelectItem value="30">30 minutes</SelectItem>
                    <SelectItem value="60">1 hour</SelectItem>
                    <SelectItem value="120">2 hours</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500">Automatically log out after inactivity</p>
              </div>

              <Separator />

              <div>
                <Label className="text-base font-medium">Password</Label>
                <p className="text-sm text-slate-500 mb-3">Change your account password</p>
                <Button variant="outline">
                  <Key className="w-4 h-4 mr-2" />
                  Change Password
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Compliance Tab */}
        <TabsContent value="compliance">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5 text-emerald-600" />
                Compliance Settings
              </CardTitle>
              <CardDescription>
                Configure compliance analysis preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>Default Framework</Label>
                <Select 
                  value={settings.defaultFramework} 
                  onValueChange={(value) => updateSetting('defaultFramework', value)}
                >
                  <SelectTrigger className="w-64">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Frameworks</SelectItem>
                    <SelectItem value="NCA ECC">NCA ECC</SelectItem>
                    <SelectItem value="ISO 27001">ISO 27001</SelectItem>
                    <SelectItem value="NIST 800-53">NIST 800-53</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500">Default framework for new analyses</p>
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Auto-Analysis</Label>
                  <p className="text-sm text-slate-500">Automatically analyze policies when uploaded</p>
                </div>
                <Switch
                  checked={settings.autoAnalysis}
                  onCheckedChange={(checked) => updateSetting('autoAnalysis', checked)}
                />
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Confidence Threshold</Label>
                <Select 
                  value={settings.confidenceThreshold} 
                  onValueChange={(value) => updateSetting('confidenceThreshold', value)}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0.5">50% (More results)</SelectItem>
                    <SelectItem value="0.6">60% (Balanced)</SelectItem>
                    <SelectItem value="0.7">70% (More accurate)</SelectItem>
                    <SelectItem value="0.8">80% (High precision)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-sm text-slate-500">Mappings below this threshold require human review</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Display Tab */}
        <TabsContent value="display">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="w-5 h-5 text-emerald-600" />
                Display Settings
              </CardTitle>
              <CardDescription>
                Customize the application appearance
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>Language</Label>
                <Select 
                  value={settings.language} 
                  onValueChange={(value) => updateSetting('language', value)}
                >
                  <SelectTrigger className="w-48">
                    <Globe className="w-4 h-4 mr-2" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Date Format</Label>
                <Select 
                  value={settings.dateFormat} 
                  onValueChange={(value) => updateSetting('dateFormat', value)}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="MM/dd/yyyy">MM/DD/YYYY</SelectItem>
                    <SelectItem value="dd/MM/yyyy">DD/MM/YYYY</SelectItem>
                    <SelectItem value="yyyy-MM-dd">YYYY-MM-DD</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>Theme</Label>
                <Select 
                  value={settings.theme} 
                  onValueChange={(value) => updateSetting('theme', value)}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">Light</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="system">System Default</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}