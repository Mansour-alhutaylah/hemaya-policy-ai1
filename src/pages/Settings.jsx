import React, { useState, useEffect } from 'react';
import { api } from '@/api/apiClient';
import { useAuth } from '@/lib/AuthContext';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/use-toast';
import PasswordStrengthChecker from '@/components/ui/PasswordStrengthChecker';
import {
  User,
  Key,
  Mail,
  Phone,
  Loader2,
} from 'lucide-react';

export default function Settings() {
  const { user: ctxUser, login } = useAuth();
  const [user, setUser] = useState(ctxUser || null);
  const [loadingPassword, setLoadingPassword] = useState(false);
  const { toast } = useToast();

  const [pwd, setPwd] = useState({ current: '', next: '', confirm: '' });

  useEffect(() => {
    let cancelled = false;
    const loadUser = async () => {
      try {
        const userData = await api.auth.me();
        if (cancelled) return;
        setUser(userData);
        const token = localStorage.getItem('token');
        if (token) login({ token, user: userData });
      } catch {
        // fall back to cached ctx user
      }
    };
    loadUser();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChangePassword = async (e) => {
    e.preventDefault();

    if (!pwd.current || !pwd.next || !pwd.confirm) {
      toast({
        title: 'Missing fields',
        description: 'Please fill in all password fields.',
        variant: 'destructive',
      });
      return;
    }
    if (pwd.next !== pwd.confirm) {
      toast({
        title: 'Passwords do not match',
        description: 'New password and confirmation must be identical.',
        variant: 'destructive',
      });
      return;
    }
    if (pwd.next === pwd.current) {
      toast({
        title: 'Choose a different password',
        description: 'New password must differ from the current one.',
        variant: 'destructive',
      });
      return;
    }

    setLoadingPassword(true);
    try {
      await api.auth.changePassword({
        current_password: pwd.current,
        new_password: pwd.next,
      });
      toast({
        title: 'Password updated',
        description: 'Your password has been changed successfully.',
      });
      setPwd({ current: '', next: '', confirm: '' });
    } catch (err) {
      // Surface the backend's user-facing message (e.g. "Current password is
      // incorrect.") but never the raw stack/JSON shape.
      const msg =
        typeof err?.message === 'string' && err.message.length < 200
          ? err.message
          : 'Could not update password. Please try again.';
      toast({
        title: 'Could not update password',
        description: msg,
        variant: 'destructive',
      });
    } finally {
      setLoadingPassword(false);
    }
  };

  const fullName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || '';

  return (
    <PageContainer
      title="Settings"
      subtitle="Manage your account"
    >
      <div className="space-y-6 max-w-3xl">
        {/* Profile Information — read-only by design; admin owns these fields */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Profile Information
            </CardTitle>
            <CardDescription>Your account details on file</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Phase UI-9: single explanation banner replaces the per-field
                "contact support" repeated across multiple captions. Cleaner
                visually and answers "why are these greyed out?" in one place. */}
            <p className="text-xs text-muted-foreground bg-muted/40 border border-border/60 rounded-lg px-3 py-2">
              Your profile is managed by your organisation. Contact your
              administrator if you need any of these fields changed.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label>Full Name</Label>
                <Input value={fullName} disabled className="bg-muted/50" />
              </div>

              <div className="space-y-2">
                <Label>Email Address</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    value={user?.email || ''}
                    disabled
                    className="pl-10 bg-muted/50"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Phone</Label>
                <div className="relative">
                  <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    value={user?.phone || ''}
                    disabled
                    className="pl-10 bg-muted/50"
                    placeholder="Not provided"
                  />
                </div>
              </div>
            </div>

            <Separator />

            <div>
              <Label className="text-base font-medium">Role</Label>
              <div className="flex items-center gap-2 mt-2">
                <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300 capitalize">
                  {user?.role || 'User'}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Change Password */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Change Password
            </CardTitle>
            <CardDescription>
              Use a strong password you don&apos;t use elsewhere
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="current-password">Current Password</Label>
                <Input
                  id="current-password"
                  type="password"
                  value={pwd.current}
                  onChange={(e) =>
                    setPwd((p) => ({ ...p, current: e.target.value }))
                  }
                  autoComplete="current-password"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  value={pwd.next}
                  onChange={(e) =>
                    setPwd((p) => ({ ...p, next: e.target.value }))
                  }
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
                <PasswordStrengthChecker password={pwd.next} />
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={pwd.confirm}
                  onChange={(e) =>
                    setPwd((p) => ({ ...p, confirm: e.target.value }))
                  }
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
                {pwd.confirm && pwd.next !== pwd.confirm && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    Passwords do not match.
                  </p>
                )}
              </div>

              <div className="pt-2">
                <Button
                  type="submit"
                  disabled={loadingPassword}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  {loadingPassword ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Key className="w-4 h-4 mr-2" />
                  )}
                  Update Password
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
