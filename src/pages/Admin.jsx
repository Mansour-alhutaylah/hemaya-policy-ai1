import React, { useState, useEffect, useCallback, Component } from 'react';
import { useToast } from '@/components/ui/use-toast';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/lib/AuthContext';
import ThemeToggle from '@/components/ThemeToggle';
import { downloadAuditTrailPdf } from '@/lib/auditReport';
import {
  buildPolicyReport,
  fetchPolicyReportData,
  triggerBrowserDownload,
} from '@/lib/policyReport';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  LayoutDashboard,
  Users,
  FileText,
  Shield,
  BarChart3,
  ClipboardList,
  Settings,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Eye,
  Edit,
  RefreshCw,
  Download,
  Upload,
  UserCheck,
  UserX,
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  XCircle,
  TrendingUp,
  Activity,
  Database,
  Lock,
  Bell,
  User,
  Plus,
  LogOut,
  Loader2,
  ArrowRight,
  KeyRound,
  Sliders,
  FileBarChart,
} from 'lucide-react';
import { format } from 'date-fns';

const ADMIN_EMAIL = 'himayaadmin@gmail.com';

// ─────────────────────────────────────────────────────────
// API HELPER — authenticated fetch wrapper for admin routes
// ─────────────────────────────────────────────────────────

// Shared 401 handler: clear storage and redirect to login with reason
function handleUnauthorized() {
  try { sessionStorage.setItem("logout_reason", "expired"); } catch { /* unavailable */ }
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  localStorage.removeItem("session_timeout_minutes");
  window.location.href = "/login";
}

async function adminFetch(path, options = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body && !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

const adminApi = {
  get:    (path)        => adminFetch(path),
  patch:  (path, data)  => adminFetch(path, { method: 'PATCH',  body: JSON.stringify(data) }),
  delete: (path)        => adminFetch(path, { method: 'DELETE' }),
  post:   (path, data)  => adminFetch(path, { method: 'POST',   body: JSON.stringify(data) }),
};

// ─────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────

const statusColors = {
  analyzed:   'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  uploaded:   'bg-blue-500/20 text-blue-400 border-blue-500/30',
  processing: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  failed:     'bg-red-500/20 text-red-400 border-red-500/30',
  pending:    'bg-slate-500/20 text-muted-foreground border-slate-500/30',
  success:    'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  error:      'bg-red-500/20 text-red-400 border-red-500/30',
  info:       'bg-blue-500/20 text-blue-400 border-blue-500/30',
  warning:    'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
};

const StatusPill = ({ status, label }) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${statusColors[status] || statusColors.pending}`}>
    {label || status}
  </span>
);

// Admin stat card — mirrors the Executive Dashboard KpiCard pattern so the
// admin panel reads as part of the same design system: dark/light card
// surface, a thin colored left stripe for semantic meaning, a translucent
// icon halo (the accent color at ~15% opacity), and theme-token typography.
//
// `accent` is a CSS color string (hex). The translucent icon background is
// derived as `${accent}26` (≈15%) so a single prop drives bar + halo + glyph.
const StatCard = ({ icon: Icon, label, value, accent = '#10b981' }) => (
  <div
    className="bg-card border border-border rounded-xl p-5 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow duration-200"
    style={{ borderLeftWidth: 3, borderLeftColor: accent }}
  >
    <div
      className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
      style={{ backgroundColor: `${accent}26` }}
    >
      <Icon className="w-5 h-5" style={{ color: accent }} />
    </div>
    <div className="min-w-0">
      <p className="text-muted-foreground text-[11px] font-medium uppercase tracking-wider">
        {label}
      </p>
      <p
        className="text-foreground text-2xl font-bold mt-1 leading-none tabular-nums"
        style={{ fontVariantNumeric: 'lining-nums tabular-nums' }}
      >
        {value}
      </p>
    </div>
  </div>
);

const SectionHeader = ({ title, subtitle }) => (
  <div className="mb-6">
    <h2 className="text-xl font-bold text-foreground">{title}</h2>
    {subtitle && <p className="text-muted-foreground text-sm mt-1">{subtitle}</p>}
  </div>
);

const LoadingRows = ({ cols = 5 }) => (
  <>
    {[1, 2, 3, 4].map(i => (
      <tr key={i} className="border-b border-border/60">
        {Array.from({ length: cols }).map((_, j) => (
          <td key={j} className="px-4 py-3">
            <div className="h-4 bg-muted rounded animate-pulse" style={{ width: `${60 + (j * 7) % 30}%` }} />
          </td>
        ))}
      </tr>
    ))}
  </>
);

const ErrorMsg = ({ msg }) => (
  <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center gap-2">
    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
    {msg}
  </div>
);

// format date — always English locale
const fmt = (d) => {
  try { return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return '—'; }
};
const fmtTime = (d) => {
  try { return new Date(d).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return '—'; }
};

// ─────────────────────────────────────────────────────────
// SECTION ERROR BOUNDARY
// Wraps each admin section so any runtime crash inside a section shows
// a usable error UI instead of unmounting the whole admin tree (which
// otherwise leaves the user staring at a blank white screen).
// ─────────────────────────────────────────────────────────

class SectionErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    // Surface the error in the dev console; the UI below replaces the section.
    // eslint-disable-next-line no-console
    console.error('[Admin section crashed]', this.props.sectionName, error, info);
  }
  componentDidUpdate(prevProps) {
    if (prevProps.sectionName !== this.props.sectionName && this.state.error) {
      this.setState({ error: null });
    }
  }
  render() {
    if (this.state.error) {
      const msg = this.state.error?.message || String(this.state.error);
      return (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-foreground/90">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-red-300 font-semibold">
                The {this.props.sectionName || 'admin'} section ran into an error.
              </p>
              <p className="text-sm text-muted-foreground mt-1 break-words">{msg}</p>
              <div className="mt-4 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="border-border text-foreground/90 hover:bg-muted"
                  onClick={() => this.setState({ error: null })}
                >
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-border text-foreground/90 hover:bg-muted"
                  onClick={() => window.location.reload()}
                >
                  Reload page
                </Button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─────────────────────────────────────────────────────────
// SECTION: DASHBOARD (admin landing page — Home-page style)
// ─────────────────────────────────────────────────────────

// Admin feature cards — one per actual admin sidebar item (skipping
// "Dashboard" since that IS this page). The labels, icons, and `target`
// section ids come straight from SIDEBAR_ITEMS so we never drift out of
// sync with the navigation. No duplicates, no invented sections.
const ADMIN_FEATURE_CARDS = [
  {
    label: 'Users',
    description: 'Manage user accounts, status, and access.',
    target: 'users',
    icon: Users,
    accent: 'from-blue-500 to-indigo-600',
  },
  {
    label: 'Policies',
    description: 'View and manage uploaded policy documents.',
    target: 'policies',
    icon: FileText,
    accent: 'from-violet-500 to-purple-600',
  },
  {
    label: 'Frameworks',
    description: 'Manage compliance frameworks and mappings.',
    target: 'frameworks',
    icon: Shield,
    accent: 'from-emerald-500 to-teal-600',
  },
  {
    label: 'Analysis Results',
    description: 'Review policy analysis outputs and findings.',
    target: 'analyses',
    icon: BarChart3,
    accent: 'from-cyan-500 to-blue-600',
  },
  {
    label: 'Activity Logs',
    description: 'Track system and admin activity logs.',
    target: 'logs',
    icon: ClipboardList,
    accent: 'from-amber-500 to-orange-600',
  },
  {
    label: 'Settings',
    description: 'Configure platform and admin preferences.',
    target: 'settings',
    icon: Settings,
    accent: 'from-rose-500 to-red-600',
  },
];

function DashboardSection({ goTo }) {
  return (
    <div>
      {/* ─── Hero — matches the Home page's slate→emerald→teal gradient
            exactly: rounded-2xl, radial emerald glow at top-right, frosted
            badge, white headline + slate-300 body, emerald primary + glassy
            secondary CTA, gradient shield icon block on the right. */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-900 to-teal-900 p-8 lg:p-10 mb-8 shadow-sm">
        <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.4),_transparent_60%)]" />
        <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 backdrop-blur px-3 py-1 text-xs font-medium text-emerald-200 ring-1 ring-white/10">
              <ShieldCheck className="w-3.5 h-3.5" />
              Himaya · Admin Panel
            </div>
            <h1 className="mt-4 text-3xl lg:text-4xl font-bold text-white tracking-tight">
              Admin Control Center
            </h1>
            <p className="mt-3 text-slate-300 text-sm lg:text-base max-w-xl">
              Manage users, policies, frameworks, analysis results, activity
              logs, and platform settings from one secure workspace.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => goTo?.('users')}
                className="inline-flex items-center justify-center rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 shadow-md shadow-emerald-500/20 transition-colors"
              >
                <Users className="w-4 h-4 mr-2" />
                Manage Users
              </button>
              <button
                type="button"
                onClick={() => goTo?.('logs')}
                className="inline-flex items-center justify-center rounded-md bg-white/5 border border-white/20 text-white hover:bg-white/10 text-sm font-medium px-4 py-2 transition-colors"
              >
                View Activity Logs
                <ArrowRight className="w-4 h-4 ml-2" />
              </button>
            </div>
          </div>
          <div className="hidden lg:flex w-24 h-24 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-600 shadow-lg shadow-emerald-500/30">
            <ShieldCheck className="w-12 h-12 text-white" />
          </div>
        </div>
      </div>

      {/* ─── Feature cards — one card per actual admin sidebar item (no
            duplicates). Same chrome as the Home page primary actions:
            bg-card + border-border + rounded-xl + shadow-sm + hover lift,
            gradient icon square top-left, bold label, muted description,
            arrow that slides in on hover. Theme tokens drive both modes. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {ADMIN_FEATURE_CARDS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              onClick={() => goTo?.(item.target)}
              className="group text-left h-full bg-card border border-border rounded-xl shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-emerald-400/50 dark:hover:border-emerald-500/40 p-5"
            >
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${item.accent} flex items-center justify-center shadow-sm mb-4`}>
                <Icon className="w-5 h-5 text-white" />
              </div>
              <div className="flex items-center gap-2">
                <p className="font-semibold text-foreground">{item.label}</p>
                <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
              </div>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                {item.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: USERS — real database data
// ─────────────────────────────────────────────────────────

function UsersSection() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [editUser, setEditUser] = useState(null);
  const [editRole, setEditRole] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Real API call → GET /api/admin/users
    adminApi.get('/admin/users')
      .then(setUsers)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = users.filter(u =>
    `${u.first_name ?? ''} ${u.last_name ?? ''} ${u.email ?? ''}`.toLowerCase().includes(search.toLowerCase())
  );

  const handleSaveRole = async () => {
    setSaving(true);
    try {
      // Real API call → PATCH /api/admin/users/{id}/role
      await adminApi.patch(`/admin/users/${editUser.id}/role`, { role: editRole });
      setUsers(prev => prev.map(u => u.id === editUser.id ? { ...u, role: editRole } : u));
      setEditUser(null);
    } catch (e) {
      alert('Failed to update role: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (u) => {
    try {
      // Real API call → PATCH /api/admin/users/{id}/status
      await adminApi.patch(`/admin/users/${u.id}/status`, { is_active: !u.is_active });
      setUsers(prev => prev.map(x => x.id === u.id ? { ...x, is_active: !u.is_active } : x));
    } catch (e) {
      alert('Failed to update status: ' + e.message);
    }
  };

  const handleDelete = async () => {
    try {
      // Real API call → DELETE /api/admin/users/{id}
      await adminApi.delete(`/admin/users/${deleteTarget}`);
      setUsers(prev => prev.filter(u => u.id !== deleteTarget));
      setDeleteTarget(null);
    } catch (e) {
      alert('Failed to delete user: ' + e.message);
    }
  };

  return (
    <div>
      <SectionHeader
        title="User Management"
        subtitle={loading ? 'Loading users…' : `${users.length} registered users`}
      />

      {error && <div className="mb-4"><ErrorMsg msg={error} /></div>}

      <div className="relative max-w-sm mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by name or email…"
          className="pl-9 bg-card border-border text-foreground placeholder:text-muted-foreground focus-visible:ring-emerald-500"
        />
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/50">
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">User</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Role</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Status</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Joined</th>
                <th className="text-right px-4 py-3 text-muted-foreground font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRows cols={5} />
              ) : filtered.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">No users found.</td></tr>
              ) : (
                filtered.map(u => (
                  <tr key={u.id} className="border-b border-border/60 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-foreground font-medium">
                          {[u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}
                        </p>
                        <p className="text-muted-foreground text-xs">{u.email}</p>
                        <p className="text-muted-foreground/70 text-[10px] font-mono">{String(u.id).slice(0, 8)}…</p>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-foreground/80">{u.role || 'Regular User'}</td>
                    <td className="px-4 py-3">
                      <StatusPill
                        status={u.is_active ? 'success' : 'error'}
                        label={u.is_active ? 'Active' : 'Inactive'}
                      />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{fmt(u.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="ghost"
                          className="text-muted-foreground hover:text-foreground h-8 px-2"
                          title="Edit role"
                          onClick={() => { setEditUser(u); setEditRole(u.role || 'Regular User'); }}>
                          <Edit className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost"
                          className={`h-8 px-2 ${u.is_active ? 'text-yellow-400 hover:text-yellow-300' : 'text-emerald-400 hover:text-emerald-300'}`}
                          onClick={() => handleToggleActive(u)}
                          title={u.is_active ? 'Deactivate' : 'Activate'}>
                          {u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                        </Button>
                        <Button size="sm" variant="ghost"
                          className="text-red-400 hover:text-red-300 h-8 px-2"
                          title="Delete user"
                          onClick={() => setDeleteTarget(u.id)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Role Dialog */}
      <Dialog open={!!editUser} onOpenChange={() => setEditUser(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">Edit User Role</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-muted-foreground text-sm">
              Changing role for <strong className="text-foreground">
                {[editUser?.first_name, editUser?.last_name].filter(Boolean).join(' ') || editUser?.email}
              </strong>
            </p>
            <Select value={editRole} onValueChange={setEditRole}>
              <SelectTrigger className="bg-muted border-border text-foreground">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-muted border-border text-foreground">
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="Compliance Officer">Compliance Officer</SelectItem>
                <SelectItem value="Auditor">Auditor</SelectItem>
                <SelectItem value="user">Regular User</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)}
              className="border-border text-foreground/80 hover:bg-muted">Cancel</Button>
            <Button onClick={handleSaveRole} disabled={saving}
              className="bg-emerald-600 hover:bg-emerald-700">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Role'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="w-5 h-5" /> Confirm Delete
            </DialogTitle>
          </DialogHeader>
          <p className="text-foreground/80 py-2">This will permanently delete the user and all their data. This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}
              className="border-border text-foreground/80 hover:bg-muted">Cancel</Button>
            <Button onClick={handleDelete} className="bg-red-600 hover:bg-red-700">Delete User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: POLICIES — real database data
// ─────────────────────────────────────────────────────────

function PoliciesSection() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [reanalyzing, setReanalyzing] = useState(null);

  useEffect(() => {
    // Real API call → GET /api/admin/policies
    adminApi.get('/admin/policies')
      .then(setPolicies)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = policies.filter(p =>
    (p.file_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (p.department ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async () => {
    try {
      // Real API call → DELETE /api/admin/policies/{id}
      await adminApi.delete(`/admin/policies/${deleteTarget}`);
      setPolicies(prev => prev.filter(p => p.id !== deleteTarget));
      setDeleteTarget(null);
    } catch (e) {
      alert('Failed to delete policy: ' + e.message);
    }
  };

  const handleReanalyze = async (id) => {
    setReanalyzing(id);
    try {
      // Real API call → POST /api/admin/policies/{id}/reanalyze
      await adminApi.post(`/admin/policies/${id}/reanalyze`, {
        frameworks: ['NCA ECC', 'ISO 27001', 'NIST 800-53'],
      });
      // Refresh status
      const fresh = await adminApi.get('/admin/policies');
      setPolicies(fresh);
    } catch (e) {
      alert('Re-analysis failed: ' + e.message);
    } finally {
      setReanalyzing(null);
    }
  };

  const policyStatus = (s) => {
    if (s === 'analyzed') return 'success';
    if (s === 'failed')   return 'error';
    if (s === 'processing') return 'warning';
    return 'info';
  };

  return (
    <div>
      <SectionHeader
        title="Policy Management"
        subtitle={loading ? 'Loading policies…' : `${policies.length} uploaded policies`}
      />

      {error && <div className="mb-4"><ErrorMsg msg={error} /></div>}

      <div className="relative max-w-sm mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by file name or department…"
          className="pl-9 bg-card border-border text-foreground placeholder:text-muted-foreground focus-visible:ring-emerald-500" />
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/50">
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">File Name</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Department</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Uploaded By</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Uploaded</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Framework</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Status</th>
                <th className="text-right px-4 py-3 text-muted-foreground font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRows cols={7} />
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">No policies found.</td></tr>
              ) : (
                filtered.map(p => (
                  <tr key={p.id} className="border-b border-border/60 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                        <div>
                          <p className="text-foreground font-medium truncate max-w-[180px]">{p.file_name}</p>
                          <p className="text-muted-foreground/70 text-[10px] font-mono">{String(p.id).slice(0, 8)}…</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{p.department || '—'}</td>
                    <td className="px-4 py-3 text-foreground/80 text-xs">{p.uploaded_by || <span className="text-muted-foreground/70">Unknown</span>}</td>
                    <td className="px-4 py-3 text-muted-foreground">{fmt(p.created_at)}</td>
                    <td className="px-4 py-3">
                      {p.framework
                        ? <span className="text-xs bg-muted text-foreground/80 px-2 py-1 rounded">{p.framework}</span>
                        : <span className="text-muted-foreground/70 text-xs">—</span>
                      }
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill
                        status={policyStatus(p.status)}
                        label={(p.status || 'unknown').charAt(0).toUpperCase() + (p.status || 'unknown').slice(1)}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="ghost"
                          className="text-blue-400 hover:text-blue-300 h-8 px-2"
                          title="Re-analyze"
                          disabled={reanalyzing === p.id}
                          onClick={() => handleReanalyze(p.id)}>
                          {reanalyzing === p.id
                            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            : <RefreshCw className="w-3.5 h-3.5" />}
                        </Button>
                        <Button size="sm" variant="ghost"
                          className="text-red-400 hover:text-red-300 h-8 px-2"
                          onClick={() => setDeleteTarget(p.id)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="w-5 h-5" /> Confirm Delete
            </DialogTitle>
          </DialogHeader>
          <p className="text-foreground/80 py-2">This will permanently delete the policy and all its analysis data.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}
              className="border-border text-foreground/80 hover:bg-muted">Cancel</Button>
            <Button onClick={handleDelete} className="bg-red-600 hover:bg-red-700">Delete Policy</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: FRAMEWORKS (uses real data from backend)
// ─────────────────────────────────────────────────────────

function FrameworksSection() {
  const { toast } = useToast();
  const [frameworks, setFrameworks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // View modal state
  const [viewFw, setViewFw] = useState(null);       // framework object from list
  const [viewDetail, setViewDetail] = useState(null); // full detail from /frameworks/{id}
  const [viewLoading, setViewLoading] = useState(false);

  // Add Control modal state
  const [addCtrlFw, setAddCtrlFw] = useState(null); // framework to add control to
  const [ctrlForm, setCtrlForm] = useState({ control_code: '', title: '', severity_if_missing: 'Medium' });
  const [ctrlSaving, setCtrlSaving] = useState(false);

  // Add / Edit framework metadata modal state
  const [editFw, setEditFw] = useState(null);       // null = closed; {} = adding; {id,...} = editing
  const [fwForm, setFwForm] = useState({ name: '', description: '' });
  const [fwSaving, setFwSaving] = useState(false);

  // File upload / replace state — frameworks are uploaded reference documents.
  // uploadFw === { mode: 'new' | 'replace', framework?: object }
  const [uploadFw, setUploadFw] = useState(null);
  const [uploadForm, setUploadForm] = useState({ name: '', description: '', version: '', file: null });
  const [uploadSaving, setUploadSaving] = useState(false);

  // Delete confirmation
  const [deleteFw, setDeleteFw] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const loadFrameworks = useCallback(() => {
    setLoading(true);
    setError(null);
    return adminApi.get('/admin/frameworks')
      .then((data) => setFrameworks(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message || 'Failed to load frameworks'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadFrameworks(); }, [loadFrameworks]);

  const openUploadNew = () => {
    setUploadFw({ mode: 'new' });
    setUploadForm({ name: '', description: '', version: '', file: null });
  };

  const openReplace = (fw) => {
    setUploadFw({ mode: 'replace', framework: fw });
    setUploadForm({ name: fw.name, description: fw.description || '', version: fw.version || '', file: null });
  };

  const openEdit = (fw) => {
    setEditFw(fw);
    setFwForm({ name: fw.name || '', description: fw.description || '' });
  };

  const submitUpload = async () => {
    const isReplace = uploadFw?.mode === 'replace';
    const targetName = isReplace ? uploadFw.framework.name : uploadForm.name.trim();
    if (!targetName) {
      toast({ title: 'Name required', description: 'Give the framework a name.', variant: 'destructive' });
      return;
    }
    if (!uploadForm.file) {
      toast({ title: 'File required', description: 'Select the reference document.', variant: 'destructive' });
      return;
    }
    setUploadSaving(true);
    try {
      // For new frameworks we create the row first so the upload's UPDATE-by-name can find it.
      if (!isReplace) {
        await adminApi.post('/admin/frameworks', {
          name: targetName,
          description: uploadForm.description,
        });
      } else if (uploadForm.description !== (uploadFw.framework.description || '')) {
        await adminApi.patch(`/admin/frameworks/${uploadFw.framework.id}`, {
          description: uploadForm.description,
        });
      }

      const token = localStorage.getItem('token');
      const form = new FormData();
      form.append('file', uploadForm.file);
      form.append('framework', targetName);
      form.append('description', uploadForm.description || '');
      form.append('version', uploadForm.version || '');
      const res = await fetch('/api/functions/upload_framework_doc', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        let msg = 'Upload failed';
        try { msg = (await res.json())?.detail || msg; } catch { /* ignore */ }
        throw new Error(msg);
      }
      const result = await res.json();
      toast({
        title: isReplace ? 'Framework Replaced' : 'Framework Uploaded',
        description: `${targetName}: ${result.chunks_created || 0} chunks indexed.`,
      });
      setUploadFw(null);
      loadFrameworks();
    } catch (e) {
      toast({
        title: 'Upload Failed',
        description: e.message || 'Could not upload the framework document.',
        variant: 'destructive',
      });
    } finally {
      setUploadSaving(false);
    }
  };

  const saveFramework = async () => {
    const name = fwForm.name.trim();
    if (!name) return;
    setFwSaving(true);
    try {
      if (editFw && editFw.id) {
        await adminApi.patch(`/admin/frameworks/${editFw.id}`, {
          name,
          description: fwForm.description,
        });
        toast({ title: 'Framework Updated', description: `'${name}' has been saved.` });
      } else {
        await adminApi.post('/admin/frameworks', {
          name,
          description: fwForm.description,
        });
        toast({ title: 'Framework Added', description: `'${name}' is now available.` });
      }
      setEditFw(null);
      loadFrameworks();
    } catch (e) {
      toast({
        title: 'Save Failed',
        description: e.message || 'Could not save the framework.',
        variant: 'destructive',
      });
    } finally {
      setFwSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteFw) return;
    setDeleting(true);
    try {
      await adminApi.delete(`/admin/frameworks/${deleteFw.id}`);
      toast({ title: 'Framework Deleted', description: `'${deleteFw.name}' was removed.` });
      setDeleteFw(null);
      loadFrameworks();
    } catch (e) {
      toast({
        title: 'Delete Failed',
        description: e.message || 'Could not delete the framework.',
        variant: 'destructive',
      });
    } finally {
      setDeleting(false);
    }
  };

  const openView = (fw) => {
    setViewFw(fw);
    setViewDetail(null);
    setViewLoading(true);
    adminApi.get(`/admin/frameworks/${fw.id}`)
      .then(setViewDetail)
      .catch(() => setViewDetail(null))
      .finally(() => setViewLoading(false));
  };

  const openAddControl = (fw) => {
    setAddCtrlFw(fw);
    setCtrlForm({ control_code: '', title: '', severity_if_missing: 'Medium' });
  };

  const saveControl = async () => {
    if (!ctrlForm.control_code.trim() || !ctrlForm.title.trim()) return;
    setCtrlSaving(true);
    try {
      await adminApi.post(`/admin/frameworks/${addCtrlFw.id}/controls`, ctrlForm);
      setAddCtrlFw(null);
      loadFrameworks();
    } catch (e) {
      alert('Failed to add control: ' + e.message);
    } finally {
      setCtrlSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Framework Management</h2>
          <p className="text-muted-foreground text-sm mt-1">
            Frameworks are uploaded reference documents stored in the database.
          </p>
        </div>
        <Button
          onClick={openUploadNew}
          className="bg-emerald-600 hover:bg-emerald-700 text-foreground flex-shrink-0"
        >
          <Plus className="w-4 h-4 mr-1.5" /> Upload Framework
        </Button>
      </div>
      {error && <div className="mb-4"><ErrorMsg msg={error} /></div>}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {loading
          ? Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-xl p-5 space-y-3">
                <div className="w-10 h-10 bg-muted rounded-lg animate-pulse" />
                <div className="h-5 bg-muted rounded animate-pulse w-1/2" />
                <div className="h-3 bg-muted rounded animate-pulse" />
                <div className="grid grid-cols-2 gap-3">
                  <div className="h-16 bg-muted rounded animate-pulse" />
                  <div className="h-16 bg-muted rounded animate-pulse" />
                </div>
              </div>
            ))
          : frameworks.length === 0
            ? <div className="col-span-3 py-12 text-center text-muted-foreground">No frameworks found in the database.</div>
            : frameworks.map(fw => {
              const hasFile = !!fw.file_url;
              return (
              <div key={fw.id} className="bg-card border border-border rounded-xl p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 bg-emerald-500/20 rounded-lg flex items-center justify-center">
                    <Shield className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => openEdit(fw)}
                      className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      title="Edit name and description"
                    >
                      <Edit className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setDeleteFw(fw)}
                      className="p-1.5 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-400 transition-colors"
                      title="Delete framework"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <h3 className="text-foreground font-bold text-lg flex items-center gap-2">
                  {fw.name}
                  {fw.version && (
                    <span className="text-[10px] font-mono bg-muted text-foreground/80 px-1.5 py-0.5 rounded">
                      v{fw.version}
                    </span>
                  )}
                </h3>
                <p className="text-muted-foreground text-xs mt-1 mb-3 line-clamp-2">{fw.description || 'No description.'}</p>

                {/* File document metadata */}
                <div className={`rounded-lg p-3 mb-3 border ${hasFile ? 'bg-card/40 border-border' : 'bg-amber-500/10 border-amber-500/30'}`}>
                  {hasFile ? (
                    <>
                      <div className="flex items-center gap-2 text-foreground/80 text-xs">
                        <FileText className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        <span className="truncate font-medium">{fw.original_file_name}</span>
                        {fw.file_type && (
                          <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{fw.file_type}</span>
                        )}
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-1">
                        Uploaded {fmt(fw.uploaded_at)}{fw.uploaded_by ? ` by ${fw.uploaded_by}` : ''}
                      </p>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-amber-400 text-xs">
                      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                      <span>No reference document uploaded yet.</span>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-muted/50 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-foreground">{fw.controls}</p>
                    <p className="text-muted-foreground text-xs">Controls</p>
                  </div>
                  <div className="bg-muted/50 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-foreground">{fw.checkpoints}</p>
                    <p className="text-muted-foreground text-xs">Checkpoints</p>
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button size="sm" variant="outline"
                    className="flex-1 min-w-[110px] border-border text-foreground/80 hover:bg-muted text-xs h-8"
                    onClick={() => openReplace(fw)}>
                    <Upload className="w-3 h-3 mr-1" /> {hasFile ? 'Replace File' : 'Upload File'}
                  </Button>
                  {hasFile && (
                    <a
                      href={fw.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 min-w-[110px] inline-flex items-center justify-center gap-1 border border-border text-foreground/80 hover:bg-muted text-xs h-8 rounded-md px-3"
                    >
                      <Download className="w-3 h-3" /> Download
                    </a>
                  )}
                  <Button size="sm" variant="outline"
                    className="flex-1 min-w-[110px] border-border text-foreground/80 hover:bg-muted text-xs h-8"
                    onClick={() => openAddControl(fw)}>
                    <Plus className="w-3 h-3 mr-1" /> Add Control
                  </Button>
                  <Button size="sm" variant="outline"
                    className="flex-1 min-w-[110px] border-border text-foreground/80 hover:bg-muted text-xs h-8"
                    onClick={() => openView(fw)}>
                    <Eye className="w-3 h-3 mr-1" /> View
                  </Button>
                </div>
              </div>
            );})}
      </div>

      {/* ── Upload / Replace Framework Document Modal ── */}
      <Dialog open={!!uploadFw} onOpenChange={open => !open && !uploadSaving && setUploadFw(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {uploadFw?.mode === 'replace'
                ? `Replace document for ${uploadFw.framework.name}`
                : 'Upload Framework'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {uploadFw?.mode !== 'replace' && (
              <div>
                <label className="text-muted-foreground text-xs mb-1 block">Framework Name *</label>
                <Input
                  placeholder="e.g. PCI DSS 4.0"
                  value={uploadForm.name}
                  onChange={e => setUploadForm(f => ({ ...f, name: e.target.value }))}
                  className="bg-card border-border text-foreground"
                />
              </div>
            )}
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Description</label>
              <Textarea
                placeholder="Optional short description."
                value={uploadForm.description}
                onChange={e => setUploadForm(f => ({ ...f, description: e.target.value }))}
                className="bg-card border-border text-foreground min-h-[60px]"
              />
            </div>
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Version</label>
              <Input
                placeholder="e.g. 2024-Rev2"
                value={uploadForm.version}
                onChange={e => setUploadForm(f => ({ ...f, version: e.target.value }))}
                className="bg-card border-border text-foreground"
              />
            </div>
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Reference Document *</label>
              <input
                type="file"
                accept=".pdf,.docx,.txt,.xlsx,.xls"
                onChange={e => setUploadForm(f => ({ ...f, file: e.target.files?.[0] || null }))}
                className="block w-full text-xs text-foreground/80 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-muted file:text-foreground/90 hover:file:bg-muted"
              />
              {uploadFw?.mode === 'replace' && uploadFw.framework.original_file_name && !uploadForm.file && (
                <p className="text-[10px] text-muted-foreground mt-1">
                  Current: {uploadFw.framework.original_file_name}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setUploadFw(null)} disabled={uploadSaving}>
              Cancel
            </Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
              disabled={uploadSaving || !uploadForm.file || (uploadFw?.mode !== 'replace' && !uploadForm.name.trim())}
              onClick={submitUpload}
            >
              {uploadSaving
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Uploading…</>
                : <><Upload className="w-4 h-4 mr-1" /> {uploadFw?.mode === 'replace' ? 'Replace File' : 'Upload Framework'}</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit Framework Metadata Modal ── */}
      <Dialog open={!!editFw} onOpenChange={open => !open && !fwSaving && setEditFw(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {editFw && editFw.id ? `Edit ${editFw.name}` : 'Add Framework'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Name *</label>
              <Input
                placeholder="e.g. PCI DSS 4.0"
                value={fwForm.name}
                onChange={e => setFwForm(f => ({ ...f, name: e.target.value }))}
                className="bg-card border-border text-foreground"
              />
            </div>
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Description</label>
              <Textarea
                placeholder="Short description shown next to the framework name."
                value={fwForm.description}
                onChange={e => setFwForm(f => ({ ...f, description: e.target.value }))}
                className="bg-card border-border text-foreground min-h-[80px]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setEditFw(null)} disabled={fwSaving}>
              Cancel
            </Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
              disabled={fwSaving || !fwForm.name.trim()}
              onClick={saveFramework}
            >
              {fwSaving
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</>
                : editFw && editFw.id ? 'Save Changes' : 'Add Framework'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Framework Confirmation ── */}
      <Dialog open={!!deleteFw} onOpenChange={open => !open && !deleting && setDeleteFw(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">Delete {deleteFw?.name}?</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm py-2">
            This permanently removes the framework, its {deleteFw?.controls || 0} control
            {deleteFw?.controls === 1 ? '' : 's'}, {deleteFw?.checkpoints || 0} checkpoint
            {deleteFw?.checkpoints === 1 ? '' : 's'}, and any reference document chunks linked to it.
            Policies that are still linked to this framework will block the deletion until they
            are reassigned or removed.
          </p>
          <DialogFooter>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setDeleteFw(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 text-foreground"
              disabled={deleting}
              onClick={confirmDelete}
            >
              {deleting
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Deleting…</>
                : <><Trash2 className="w-4 h-4 mr-1" /> Delete Framework</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── View Framework Modal ── */}
      <Dialog open={!!viewFw} onOpenChange={open => !open && setViewFw(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground text-lg">{viewFw?.name}</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm mb-4">{viewFw?.description || 'No description.'}</p>
          {viewLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading controls…
            </div>
          ) : !viewDetail ? (
            <p className="text-muted-foreground text-sm">Could not load details.</p>
          ) : viewDetail.controls.length === 0 ? (
            <p className="text-muted-foreground text-sm">No controls found for this framework.</p>
          ) : (
            <div className="space-y-3">
              {viewDetail.controls.map(ctrl => (
                <div key={ctrl.id} className="bg-card/60 rounded-lg p-3 border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-emerald-400 text-xs">{ctrl.control_code}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                      ctrl.severity_if_missing === 'High' ? 'bg-red-500/20 text-red-400' :
                      ctrl.severity_if_missing === 'Critical' ? 'bg-red-700/30 text-red-300' :
                      'bg-amber-500/20 text-amber-400'
                    }`}>{ctrl.severity_if_missing}</span>
                  </div>
                  <p className="text-foreground text-sm font-medium">{ctrl.title}</p>
                  {ctrl.checkpoints.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {ctrl.checkpoints.map(cp => (
                        <li key={cp.id} className="text-muted-foreground text-xs flex gap-2">
                          <span className="text-muted-foreground/70">{cp.index}.</span>
                          {cp.requirement}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Add Control Modal ── */}
      <Dialog open={!!addCtrlFw} onOpenChange={open => !open && setAddCtrlFw(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">Add Control to {addCtrlFw?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Control ID / Code *</label>
              <Input
                placeholder="e.g. ECC-2-1-1"
                value={ctrlForm.control_code}
                onChange={e => setCtrlForm(f => ({ ...f, control_code: e.target.value }))}
                className="bg-card border-border text-foreground"
              />
            </div>
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Control Title *</label>
              <Input
                placeholder="e.g. Asset Management"
                value={ctrlForm.title}
                onChange={e => setCtrlForm(f => ({ ...f, title: e.target.value }))}
                className="bg-card border-border text-foreground"
              />
            </div>
            <div>
              <label className="text-muted-foreground text-xs mb-1 block">Severity if Missing</label>
              <Select
                value={ctrlForm.severity_if_missing}
                onValueChange={v => setCtrlForm(f => ({ ...f, severity_if_missing: v }))}>
                <SelectTrigger className="bg-card border-border text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {['Low', 'Medium', 'High', 'Critical'].map(s => (
                    <SelectItem key={s} value={s} className="text-foreground">{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setAddCtrlFw(null)}>Cancel</Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
              disabled={ctrlSaving || !ctrlForm.control_code.trim() || !ctrlForm.title.trim()}
              onClick={saveControl}>
              {ctrlSaving ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</> : 'Add Control'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: ANALYSIS RESULTS
// ─────────────────────────────────────────────────────────

function AnalysesSection() {
  const { toast } = useToast();
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);

  const loadAnalyses = useCallback(() => {
    setLoading(true);
    setError(null);
    return adminApi.get('/admin/analysis-results')
      .then(setAnalyses)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadAnalyses(); }, [loadAnalyses]);

  const handleDelete = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await adminApi.delete(`/admin/analysis-results/${deleteTarget}`);
      setAnalyses(prev => prev.filter(a => a.id !== deleteTarget));
      setDeleteTarget(null);
      toast({ title: 'Analysis Deleted', description: 'The result was removed.' });
    } catch (e) {
      toast({
        title: 'Delete Failed',
        description: e.message || 'Could not delete the analysis result.',
        variant: 'destructive',
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleDownload = async (row) => {
    if (!row.policy_id) {
      toast({
        title: 'Download Unavailable',
        description: 'This result is not linked to a policy.',
        variant: 'destructive',
      });
      return;
    }
    setDownloadingId(row.id);
    try {
      const data = await fetchPolicyReportData(row.policy_id);
      const { blob, filename } = await buildPolicyReport(data, 'pdf');
      triggerBrowserDownload(blob, filename);
      toast({
        title: 'Report Downloaded',
        description: `Branded PDF for ${row.policy_name || 'this policy'} ready.`,
      });
    } catch (e) {
      toast({
        title: 'Download Failed',
        description: e.message || 'Could not build the analysis report.',
        variant: 'destructive',
      });
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div>
      <SectionHeader title="Analysis Results" subtitle={loading ? 'Loading…' : `${analyses.length} analyses`} />
      {error && <div className="mb-4"><ErrorMsg msg={error} /></div>}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/50">
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Policy</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Uploaded By</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Framework</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Score</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium hidden md:table-cell">Compliant</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium hidden md:table-cell">Partial</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium hidden md:table-cell">Gaps</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Date</th>
                <th className="text-right px-4 py-3 text-muted-foreground font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRows cols={9} />
              ) : analyses.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-muted-foreground">No analyses found.</td></tr>
              ) : (
                analyses.map(a => {
                  const score = Number(a.compliance_score ?? a.score ?? 0);
                  return (
                    <tr key={a.id} className="border-b border-border/60 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 text-foreground text-xs max-w-[160px] truncate">{a.policy_name}</td>
                      <td className="px-4 py-3 text-foreground/80 text-xs">{a.uploaded_by || <span className="text-muted-foreground/70">Unknown</span>}</td>
                      <td className="px-4 py-3">
                        <span className="text-xs bg-muted text-foreground/80 px-2 py-1 rounded">
                          {a.framework || a.framework_id || '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-bold ${score >= 80 ? 'text-emerald-400' : score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                          {score.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-emerald-400 hidden md:table-cell">{a.controls_covered ?? a.compliant ?? '—'}</td>
                      <td className="px-4 py-3 text-yellow-400 hidden md:table-cell">{a.controls_partial ?? a.partial ?? '—'}</td>
                      <td className="px-4 py-3 text-red-400 hidden md:table-cell">{a.controls_missing ?? a.non_compliant ?? '—'}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{fmt(a.analyzed_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-blue-400 hover:text-blue-300 h-8 px-2"
                            title="Download branded PDF report"
                            onClick={() => handleDownload(a)}
                            disabled={downloadingId === a.id}
                          >
                            {downloadingId === a.id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <Download className="w-3.5 h-3.5" />}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-400 hover:text-red-300 h-8 px-2"
                            title="Delete analysis result"
                            onClick={() => setDeleteTarget(a.id)}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="w-5 h-5" /> Confirm Delete
            </DialogTitle>
          </DialogHeader>
          <p className="text-foreground/80 py-2">This will permanently delete the analysis result.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}
              className="border-border text-foreground/80 hover:bg-muted">Cancel</Button>
            <Button onClick={handleDelete} disabled={deleting} className="bg-red-600 hover:bg-red-700">
              {deleting
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Deleting…</>
                : 'Delete Result'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: ACTIVITY LOGS — real database data
// ─────────────────────────────────────────────────────────

// Humanize raw audit-log action codes for display.
const ACTION_LABELS = {
  policy_upload: 'Policy Upload',
  policy_delete: 'Policy Delete',
  analysis_start: 'Analysis Started',
  analysis_complete: 'Analysis Complete',
  analysis_delete: 'Analysis Deleted',
  mapping_review: 'Mapping Review',
  report_generate: 'Report Generated',
  report_delete: 'Report Deleted',
  framework_upload: 'Framework Uploaded',
  framework_delete: 'Framework Deleted',
  gap_update: 'Gap Update',
  settings_change: 'Settings Change',
  user_login: 'User Login',
  user_logout: 'User Logout',
};

function readableAction(action) {
  if (!action) return '—';
  return (
    ACTION_LABELS[action] ||
    String(action).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

// Render audit details (string or JSON-stringified object) as a tidy line.
function formatLogDetails(details) {
  if (details == null || details === '') return '—';
  if (typeof details === 'string') {
    const t = details.trim();
    if (t.startsWith('{') || t.startsWith('[')) {
      try {
        const parsed = JSON.parse(t);
        if (parsed && typeof parsed === 'object') {
          return Object.entries(parsed)
            .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
            .join(' · ');
        }
      } catch { /* fall through */ }
    }
    return details;
  }
  if (typeof details === 'object') {
    try {
      return Object.entries(details)
        .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
        .join(' · ');
    } catch { return JSON.stringify(details); }
  }
  return String(details);
}

function LogsSection() {
  const { toast } = useToast();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    // Real API call → GET /api/admin/activity-logs
    adminApi.get('/admin/activity-logs')
      .then(setLogs)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Derive status from action text since AuditLog has no status field
  const logStatus = (action = '') => {
    const a = action.toLowerCase();
    if (a.includes('fail') || a.includes('error') || a.includes('delete')) return 'error';
    if (a.includes('role') || a.includes('admin') || a.includes('update')) return 'warning';
    if (a.includes('login') || a.includes('upload') || a.includes('complet') || a.includes('analyz')) return 'success';
    return 'info';
  };

  const enriched = logs.map(l => ({ ...l, _status: logStatus(l.action) }));
  const filtered = filter === 'all' ? enriched : enriched.filter(l => l._status === filter);

  const handleExportPdf = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      // The admin endpoint returns actor_name; the audit PDF helper expects "actor".
      const exportable = filtered.map(l => ({
        id: l.id,
        timestamp: l.timestamp,
        action: l.action,
        actor: l.actor_name || 'system',
        target_type: l.target_type,
        target_id: l.target_id,
        details: l.details,
      }));
      await downloadAuditTrailPdf(exportable, {
        action: filter !== 'all' ? filter : undefined,
      });
      toast({
        title: 'Audit Trail Exported',
        description: `${exportable.length} record${exportable.length === 1 ? '' : 's'} exported to PDF.`,
      });
    } catch (e) {
      toast({
        title: 'Export Failed',
        description: e?.message || 'Could not generate the audit PDF.',
        variant: 'destructive',
      });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Activity Logs</h2>
          <p className="text-muted-foreground text-sm mt-1">Full audit trail of system events</p>
        </div>
        <Button
          onClick={handleExportPdf}
          disabled={exporting || loading}
          className="bg-muted hover:bg-muted text-foreground border border-border flex-shrink-0"
        >
          {exporting
            ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Generating PDF…</>
            : <><Download className="w-4 h-4 mr-1.5" /> Export PDF</>}
        </Button>
      </div>

      {error && <div className="mb-4"><ErrorMsg msg={error} /></div>}

      <div className="flex gap-2 mb-4 flex-wrap">
        {['all', 'success', 'error', 'warning', 'info'].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize ${
              filter === f ? 'bg-emerald-600 text-foreground' : 'bg-muted text-muted-foreground hover:text-foreground'
            }`}>
            {f}
          </button>
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/50">
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Status</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Activity</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">User</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Target</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium hidden lg:table-cell">Details</th>
                <th className="text-left px-4 py-3 text-muted-foreground font-medium">Date &amp; Time</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRows cols={6} />
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">No logs found.</td></tr>
              ) : (
                filtered.map((log, i) => (
                  <tr key={log.id || i} className="border-b border-border/60 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <StatusPill status={log._status} label={log._status.charAt(0).toUpperCase() + log._status.slice(1)} />
                    </td>
                    <td className="px-4 py-3 text-foreground/90 font-medium">{readableAction(log.action)}</td>
                    <td className="px-4 py-3 text-foreground/80 text-xs">
                      {log.actor_name
                        ? log.actor_name
                        : <span className="text-muted-foreground/70">System</span>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {log.target_type
                        ? <>{log.target_type}{log.target_id ? <span className="text-muted-foreground/70"> · {String(log.target_id).slice(0, 8)}…</span> : null}</>
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs hidden lg:table-cell max-w-[360px] truncate" title={formatLogDetails(log.details)}>
                      {formatLogDetails(log.details)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs whitespace-nowrap">{fmtTime(log.timestamp)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// SECTION: SETTINGS
// ─────────────────────────────────────────────────────────

function SettingsSection({ adminUser }) {
  const { toast } = useToast();

  // ── Remote settings state ────────────────────────────────
  const [settings, setSettings] = useState(null);  // null = loading
  const [loadError, setLoadError] = useState(null);

  // ── Per-card saving state ────────────────────────────────
  const [savingProfile,  setSavingProfile]  = useState(false);
  const [savingAI,       setSavingAI]       = useState(false);
  const [savingNotify,   setSavingNotify]   = useState(false);
  const [savingSecurity, setSavingSecurity] = useState(false);

  // ── Controlled form values (hydrated from backend) ───────
  const [firstName, setFirstName] = useState('');
  const [lastName,  setLastName]  = useState('');

  const [llmModel,  setLlmModel]  = useState('gpt-4o-mini');
  const [topK,      setTopK]      = useState('10');

  const [notifyAnalysisComplete, setNotifyAnalysisComplete] = useState(true);
  const [notifyFailedAnalysis,   setNotifyFailedAnalysis]   = useState(true);
  const [notifyWeeklyReport,     setNotifyWeeklyReport]     = useState(false);
  const [notifyNewUser,          setNotifyNewUser]          = useState(true);

  const [sessionTimeout,  setSessionTimeout]  = useState('60');
  const [maxAttempts,     setMaxAttempts]      = useState('5');
  const [lockoutDuration, setLockoutDuration] = useState('15');

  // ── Load settings from backend on mount ──────────────────
  useEffect(() => {
    adminApi.get('/admin/settings')
      .then(data => {
        setSettings(data);
        if (data.llm_model)                setLlmModel(data.llm_model);
        if (data.top_k_retrieval)          setTopK(data.top_k_retrieval);
        if (data.notify_analysis_complete) setNotifyAnalysisComplete(data.notify_analysis_complete === 'true');
        if (data.notify_failed_analysis)   setNotifyFailedAnalysis(data.notify_failed_analysis === 'true');
        if (data.notify_weekly_report)     setNotifyWeeklyReport(data.notify_weekly_report === 'true');
        if (data.notify_new_user)          setNotifyNewUser(data.notify_new_user === 'true');
        if (data.session_timeout_minutes)  setSessionTimeout(data.session_timeout_minutes);
        if (data.max_login_attempts)       setMaxAttempts(data.max_login_attempts);
        if (data.lockout_duration_minutes) setLockoutDuration(data.lockout_duration_minutes);
      })
      .catch(e => setLoadError(e.message));

    if (adminUser) {
      setFirstName(adminUser.first_name || '');
      setLastName(adminUser.last_name || '');
    }
  }, [adminUser]);

  // ── Generic save helper ───────────────────────────────────
  const saveSettings = useCallback(async (patch, setSaving) => {
    setSaving(true);
    try {
      const updated = await adminApi.patch('/admin/settings', patch);
      setSettings(updated);
      // Update session_timeout in localStorage so AuthContext picks it up immediately
      if (patch.session_timeout_minutes) {
        localStorage.setItem('session_timeout_minutes', patch.session_timeout_minutes);
      }
      toast({ title: 'Settings saved', description: 'Changes have been applied.', variant: 'default' });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [toast]);

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      await adminApi.patch('/auth/profile', { first_name: firstName.trim(), last_name: lastName.trim() });
      toast({ title: 'Profile saved', description: 'Name updated successfully.', variant: 'default' });
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setSavingProfile(false);
    }
  };

  const numInput = (value, setter) => (
    <Input
      lang="en"
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      value={value}
      onChange={e => setter(e.target.value.replace(/\D/g, ''))}
      className="bg-muted border-border text-foreground focus-visible:ring-emerald-500"
      style={{ fontVariantNumeric: 'lining-nums' }}
    />
  );

  const Toggle = ({ checked, onChange }) => (
    <label className="relative inline-flex items-center cursor-pointer">
      <input type="checkbox" className="sr-only peer" checked={checked} onChange={e => onChange(e.target.checked)} />
      <div className="w-9 h-5 bg-muted rounded-full peer peer-checked:bg-emerald-600 transition-colors after:absolute after:top-0.5 after:left-0.5 after:bg-white after:w-4 after:h-4 after:rounded-full after:transition-all peer-checked:after:translate-x-4" />
    </label>
  );

  if (loadError) {
    return (
      <div>
        <SectionHeader title="Settings" subtitle="Platform configuration and preferences" />
        <ErrorMsg msg={`Failed to load settings: ${loadError}`} />
      </div>
    );
  }

  const isLoading = settings === null;

  return (
    <div>
      <SectionHeader title="Settings" subtitle="Platform configuration and preferences" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ── Admin Profile ── */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-emerald-500/20 rounded-lg flex items-center justify-center">
              <User className="w-5 h-5 text-emerald-400" />
            </div>
            <h3 className="text-foreground font-semibold">Admin Profile</h3>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-muted-foreground text-xs block mb-1">First Name</label>
              <Input lang="en" value={firstName} onChange={e => setFirstName(e.target.value)}
                className="bg-muted border-border text-foreground focus-visible:ring-emerald-500" />
            </div>
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Last Name</label>
              <Input lang="en" value={lastName} onChange={e => setLastName(e.target.value)}
                className="bg-muted border-border text-foreground focus-visible:ring-emerald-500" />
            </div>
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Email</label>
              <Input defaultValue={ADMIN_EMAIL} disabled className="bg-muted border-border text-muted-foreground" />
            </div>
            <Button className="w-full bg-emerald-600 hover:bg-emerald-700 mt-2"
              disabled={savingProfile} onClick={saveProfile}>
              {savingProfile ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</> : 'Save Profile'}
            </Button>
          </div>
        </div>

        {/* ── AI Model Settings ── */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-blue-500/20 rounded-lg flex items-center justify-center">
              <Database className="w-5 h-5 text-blue-400" />
            </div>
            <h3 className="text-foreground font-semibold">AI Model Settings</h3>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-muted-foreground text-xs block mb-1">LLM Model</label>
              <Select value={isLoading ? 'gpt-4o-mini' : llmModel} onValueChange={setLlmModel} disabled={isLoading}>
                <SelectTrigger className="bg-muted border-border text-foreground">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-muted border-border text-foreground">
                  <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                  <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                  <SelectItem value="gpt-4-turbo">GPT-4 Turbo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Top-K Retrieval</label>
              {numInput(topK, setTopK)}
            </div>
            <Button className="w-full bg-blue-600 hover:bg-blue-700 mt-2"
              disabled={savingAI || isLoading}
              onClick={() => saveSettings({ llm_model: llmModel, top_k_retrieval: topK }, setSavingAI)}>
              {savingAI ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</> : 'Save AI Settings'}
            </Button>
          </div>
        </div>

        {/* ── Notification Settings ── */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-yellow-500/20 rounded-lg flex items-center justify-center">
              <Bell className="w-5 h-5 text-yellow-400" />
            </div>
            <h3 className="text-foreground font-semibold">Notification Settings</h3>
          </div>
          <div className="space-y-3 text-sm">
            {[
              { label: 'Email on analysis complete', val: notifyAnalysisComplete, set: setNotifyAnalysisComplete },
              { label: 'Email on failed analysis',   val: notifyFailedAnalysis,   set: setNotifyFailedAnalysis },
              { label: 'Weekly compliance report',   val: notifyWeeklyReport,     set: setNotifyWeeklyReport },
              { label: 'New user registrations',     val: notifyNewUser,          set: setNotifyNewUser },
            ].map(item => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-foreground/80">{item.label}</span>
                <Toggle checked={item.val} onChange={item.set} />
              </div>
            ))}
          </div>
          <Button className="w-full bg-yellow-600 hover:bg-yellow-700 mt-4"
            disabled={savingNotify || isLoading}
            onClick={() => saveSettings({
              notify_analysis_complete: String(notifyAnalysisComplete),
              notify_failed_analysis:   String(notifyFailedAnalysis),
              notify_weekly_report:     String(notifyWeeklyReport),
              notify_new_user:          String(notifyNewUser),
            }, setSavingNotify)}>
            {savingNotify ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</> : 'Save Notification Settings'}
          </Button>
        </div>

        {/* ── Security Settings ── */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-red-500/20 rounded-lg flex items-center justify-center">
              <Lock className="w-5 h-5 text-red-400" />
            </div>
            <h3 className="text-foreground font-semibold">Security Settings</h3>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Session Timeout (minutes)</label>
              {numInput(sessionTimeout, setSessionTimeout)}
              <p className="text-muted-foreground/70 text-[10px] mt-1">Users are logged out after this many minutes of inactivity. Applied on next login.</p>
            </div>
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Max Login Attempts</label>
              {numInput(maxAttempts, setMaxAttempts)}
            </div>
            <div>
              <label className="text-muted-foreground text-xs block mb-1">Lockout Duration (minutes)</label>
              {numInput(lockoutDuration, setLockoutDuration)}
              <p className="text-muted-foreground/70 text-[10px] mt-1">How long an account stays locked after exceeding max attempts.</p>
            </div>
            <Button className="w-full bg-red-600 hover:bg-red-700 mt-2"
              disabled={savingSecurity || isLoading}
              onClick={() => saveSettings({
                session_timeout_minutes:  sessionTimeout  || '60',
                max_login_attempts:       maxAttempts     || '5',
                lockout_duration_minutes: lockoutDuration || '15',
              }, setSavingSecurity)}>
              {savingSecurity ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Saving…</> : 'Save Security Settings'}
            </Button>
          </div>
        </div>

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// ADMIN SIDEBAR
// ─────────────────────────────────────────────────────────

const SIDEBAR_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',       icon: LayoutDashboard },
  { id: 'users',      label: 'Users',            icon: Users },
  { id: 'policies',   label: 'Policies',         icon: FileText },
  { id: 'frameworks', label: 'Frameworks',       icon: Shield },
  { id: 'analyses',   label: 'Analysis Results', icon: BarChart3 },
  { id: 'logs',       label: 'Activity Logs',    icon: ClipboardList },
  { id: 'settings',   label: 'Settings',         icon: Settings },
];

function AdminSidebar({ active, setActive, collapsed, setCollapsed, onLogout }) {
  return (
    // Uses the same --sidebar-* token set as the user-facing Sidebar (which
    // is intentionally deep navy in BOTH light and dark mode), so the admin
    // shell is visually identical to the main app sidebar in every theme.
    <aside
      className={`fixed left-0 top-0 z-40 h-screen bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col transition-all duration-300 ${collapsed ? 'w-20' : 'w-64'}`}
    >
      {/* Brand block — same dimensions, padding, gradient tile, and
          subtitle treatment as the user Sidebar. */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-sidebar-border">
        <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-600 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20 flex-shrink-0">
          <ShieldCheck className="w-6 h-6 text-white" />
        </div>
        {!collapsed && (
          <div className="flex flex-col">
            <span className="font-bold text-lg tracking-tight text-white">Himaya</span>
            <span className="text-[10px] text-sidebar-foreground/70 uppercase tracking-widest">Admin Panel</span>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 scrollbar-thin">
        <ul className="space-y-1">
          {SIDEBAR_ITEMS.map(item => {
            const Icon = item.icon;
            const isActive = active === item.id;
            // Same exact state classes the user Sidebar uses:
            //   inactive  → text-sidebar-foreground/70 + hover:bg-sidebar-accent
            //   active    → emerald gradient pill + emerald-300 text +
            //               2 px emerald-400 left bar + emerald-300 icon
            //   inactive icon → /60, transitions to emerald-300 on hover
            return (
              <li key={item.id}>
                <button
                  onClick={() => setActive(item.id)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group relative w-full ${
                    isActive
                      ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/10 text-emerald-300 border-l-2 border-emerald-400'
                      : 'text-sidebar-foreground/70 hover:text-white hover:bg-sidebar-accent'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon
                    className={`w-5 h-5 flex-shrink-0 transition-colors ${
                      isActive
                        ? 'text-emerald-300'
                        : 'text-sidebar-foreground/60 group-hover:text-emerald-300'
                    }`}
                  />
                  {!collapsed && <span className="text-sm font-medium">{item.label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="p-3 border-t border-sidebar-border space-y-1">
        {/* Back to App — uses the same muted/hover treatment as the user
            Sidebar's footer items so it reads as part of the same surface,
            with a red accent only on the icon to flag the exit action. */}
        <button
          onClick={onLogout}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sidebar-foreground/70 hover:text-white hover:bg-sidebar-accent transition-colors"
        >
          <LogOut className="w-5 h-5 flex-shrink-0 text-red-400" />
          {!collapsed && <span className="text-sm">Back to App</span>}
        </button>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sidebar-foreground/70 hover:text-white hover:bg-sidebar-accent transition-colors"
        >
          {collapsed
            ? <ChevronRight className="w-5 h-5" />
            : <><ChevronLeft className="w-5 h-5" /><span className="text-sm">Collapse</span></>}
        </button>
      </div>
    </aside>
  );
}

// ─────────────────────────────────────────────────────────
// ACCESS DENIED
// ─────────────────────────────────────────────────────────

function AccessDenied() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center">
        <div className="w-20 h-20 bg-red-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <Lock className="w-10 h-10 text-red-400" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-2">Access Denied</h1>
        <p className="text-muted-foreground mb-6">You do not have permission to view this page.</p>
        <a href="/" className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-foreground px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
          Return to Dashboard
        </a>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// MAIN ADMIN PAGE
// ─────────────────────────────────────────────────────────

export default function Admin() {
  const { user, isAuthenticated, isLoadingAuth } = useAuth();
  const [active, setActive] = useState('dashboard');
  const [collapsed, setCollapsed] = useState(false);

  // Admin panel respects the global ThemeContext like every other page —
  // no more force-dark on mount. The toggle in the header lets the admin
  // switch themes and the choice persists via localStorage.

  if (isLoadingAuth) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-border border-t-emerald-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.email !== ADMIN_EMAIL) return <AccessDenied />;

  const renderSection = () => {
    switch (active) {
      case 'dashboard':   return <DashboardSection goTo={setActive} />;
      case 'users':       return <UsersSection />;
      case 'policies':    return <PoliciesSection />;
      case 'frameworks':  return <FrameworksSection />;
      case 'analyses':    return <AnalysesSection />;
      case 'logs':        return <LogsSection />;
      case 'settings':    return <SettingsSection adminUser={user} />;
      default:            return <DashboardSection goTo={setActive} />;
    }
  };

  return (
    // lang="en" ensures number inputs always render English (Latin) digits
    // regardless of the browser locale or OS language setting
    <div
      lang="en"
      className="min-h-screen bg-background text-foreground"
      style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
    >
      <AdminSidebar
        active={active}
        setActive={setActive}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        onLogout={() => { window.location.href = '/'; }}
      />

      <div className={`transition-all duration-300 ${collapsed ? 'ml-20' : 'ml-64'}`}>
        {/* Top bar */}
        {/* Section content rendered below is wrapped in SectionErrorBoundary
            so a crash in any single section doesn't blank the whole admin shell. */}
        {/* Topbar — slightly transparent over the page so it reads as a
            distinct band, with a stronger bottom border than the rest of the
            chrome to anchor the page hierarchy. */}
        <header className="bg-card/80 backdrop-blur supports-[backdrop-filter]:bg-card/70 border-b border-border px-6 py-4 flex items-center justify-between sticky top-0 z-30">
          <div>
            <h1 className="text-foreground font-semibold text-lg capitalize tracking-tight">{active.replace('-', ' ')}</h1>
            <p className="text-muted-foreground text-xs mt-0.5">Himaya AI — Admin Panel</p>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle variant="inline" />
            <div className="text-right">
              <p className="text-foreground text-sm font-medium">
                {user?.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : 'Admin'}
              </p>
              <p className="text-muted-foreground text-xs">{ADMIN_EMAIL}</p>
            </div>
            <div className="w-9 h-9 bg-emerald-500/20 rounded-full flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            </div>
          </div>
        </header>

        <main className="p-6">
          <SectionErrorBoundary sectionName={active}>
            {renderSection()}
          </SectionErrorBoundary>
        </main>
      </div>
    </div>
  );
}
