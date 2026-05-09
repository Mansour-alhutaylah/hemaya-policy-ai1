import React, { useState, useRef, useEffect, useCallback, useMemo, Children } from 'react';
import { api } from '@/api/apiClient';
import { useAuth } from '@/lib/AuthContext';
import { ASSISTANT_CHAT_PREFIX, purgeLegacyAssistantSessions } from '@/lib/utils';
import PageContainer from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import ReactMarkdown from 'react-markdown';
import {
  Send,
  Bot,
  User,
  Sparkles,
  AlertTriangle,
  Loader2,
  RefreshCw,
  Database,
  FileText,
  StopCircle,
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useQuery } from '@tanstack/react-query';

// Hard ceiling for any single chat call. Slightly above the backend's 50s
// asyncio.wait_for so a server-side timeout surfaces as a 504 first; this
// abort is the safety net for genuine network drops where the server never
// answers at all.
const REQUEST_TIMEOUT_MS = 75000;

// Cap stored history so a long-running session can't pile up unbounded JSON
// in sessionStorage. Older messages still showed in the current page; only
// the persisted slice is trimmed.
const MAX_PERSISTED_MESSAGES = 50;

const INITIAL_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hello! I'm your Himaya compliance assistant. Ask me about your latest analysis, gaps, framework scores, or what to fix first — I'll answer using your real data.\n\nIf you haven't run an analysis yet, upload a policy from the **Policies** page and run analysis to get specific answers.",
  type: 'greeting',
};

const SUGGESTED_QUESTIONS = [
  'What is my current compliance status?',
  'What are my top compliance gaps?',
  'Which controls should I fix first?',
  'How can I improve my NCA ECC score?',
  'Which policies have the highest risk?',
  'Explain my latest analysis results.',
];

// ── Persistence helpers (sessionStorage, scoped per user) ─────────────────
//
// We deliberately use sessionStorage instead of localStorage so the chat
// vanishes when the tab/browser closes, which matches the spec ("persist
// during the user session"). Logout paths additionally call
// clearAssistantSessions() to wipe history immediately, so a different user
// signing in on the same browser starts fresh.

function userScopeKey(user) {
  // Prefer the immutable user id; fall back to email if id isn't on the
  // cached user object yet. Without either we can't safely scope, so we
  // disable persistence for that render.
  const id = user?.id || user?.email;
  return id ? `${ASSISTANT_CHAT_PREFIX}${id}` : null;
}

// A persisted message is "transient" if it represents an error or pending
// state we don't want to resurrect across navigations. Transient bubbles get
// stripped on both save and restore, so a stale "request took too long" can
// never come back from sessionStorage.
function _isTransient(m) {
  if (!m) return true;
  if (m.type === 'error') return true;
  if (m.type === 'pending' || m.type === 'loading') return true;
  if (typeof m.content !== 'string' || m.content.trim() === '') return true;
  return false;
}

function loadPersistedMessages(key) {
  if (!key || typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    // Defensive: only keep the fields we render, drop anything transient,
    // and keep only valid roles. This protects against any older build
    // having persisted the wrong shape.
    const cleaned = parsed
      .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
      .filter((m) => !_isTransient(m))
      .map((m) => ({
        id:
          typeof m.id === 'string' || typeof m.id === 'number'
            ? m.id
            : `r-${Math.random()}`,
        role: m.role,
        content: m.content,
        type: typeof m.type === 'string' ? m.type : undefined,
        sources: Array.isArray(m.sources) ? m.sources : undefined,
      }));
    return cleaned.length ? cleaned : null;
  } catch {
    return null;
  }
}

function savePersistedMessages(key, messages) {
  if (!key || typeof window === 'undefined') return;
  try {
    // Only persist what's needed to re-render. No tokens, no system prompts,
    // no backend internals — just the visible non-transient bubbles.
    const slim = messages
      .filter((m) => !_isTransient(m))
      .slice(-MAX_PERSISTED_MESSAGES)
      .map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        type: m.type,
        sources: m.sources,
      }));
    if (slim.length === 0) {
      sessionStorage.removeItem(key);
      return;
    }
    sessionStorage.setItem(key, JSON.stringify(slim));
  } catch {
    // Quota exceeded or storage disabled — drop silently; the UI stays
    // functional, only the persistence layer is degraded.
  }
}

function clearPersistedMessages(key) {
  if (!key || typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* noop */
  }
}

// Phase F: render `[Page N]` and `[Page N · ¶M]` patterns inside an answer
// as inline emerald pill chips. Walks the children of any text-bearing
// markdown renderer (paragraph, list item, strong) so citations work
// regardless of where they appear in the answer.
const CITATION_RE = /(\[Page\s*\d+(?:\s*·\s*¶?\s*\d+)?\])/g;
function withCitations(children) {
  return Children.map(children, (child, idx) => {
    if (typeof child !== 'string') return child;
    if (!CITATION_RE.test(child)) {
      CITATION_RE.lastIndex = 0;
      return child;
    }
    CITATION_RE.lastIndex = 0;
    const parts = child.split(CITATION_RE);
    return parts.map((part, i) => {
      if (CITATION_RE.test(part)) {
        CITATION_RE.lastIndex = 0;
        const label = part.replace(/^\[|\]$/g, '');
        return (
          <span
            key={`${idx}-${i}`}
            className="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded text-[10.5px] font-medium bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/25 align-middle whitespace-nowrap"
          >
            {label}
          </span>
        );
      }
      return part;
    });
  });
}

export default function AIAssistant() {
  const { user } = useAuth();
  const storageKey = useMemo(() => userScopeKey(user), [user]);

  // Lazy initial state: hydrate from sessionStorage on first render so the
  // user sees their previous conversation immediately.
  const [messages, setMessages] = useState(() => {
    const restored = loadPersistedMessages(storageKey);
    return restored && restored.length ? restored : [INITIAL_MESSAGE];
  });
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [contextSummary, setContextSummary] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  // Phase F: per-tab policy scope. "all" means the assistant answers across
  // the user's whole portfolio; a policy id scopes it to one document.
  // Persisted in sessionStorage (per-user) so navigating away and back keeps
  // the same scope.
  const policyScopeKey = storageKey ? `${storageKey}:scope` : null;
  const [policyScope, setPolicyScope] = useState(() => {
    if (!policyScopeKey || typeof window === 'undefined') return 'all';
    try { return sessionStorage.getItem(policyScopeKey) || 'all'; }
    catch { return 'all'; }
  });
  useEffect(() => {
    if (!policyScopeKey || typeof window === 'undefined') return;
    try { sessionStorage.setItem(policyScopeKey, policyScope); } catch {}
  }, [policyScopeKey, policyScope]);

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => api.entities.Policy.list('-created_at', 50),
  });

  // If the user identity arrives after first paint (auth hydration race),
  // re-hydrate once we have a key. We compare lengths to avoid clobbering an
  // already-active conversation.
  useEffect(() => {
    if (!storageKey) return;
    const restored = loadPersistedMessages(storageKey);
    if (restored && restored.length && messages.length <= 1) {
      setMessages(restored);
    }
    // Intentionally only react to storageKey changes (user identity becoming
    // available). Re-running on every messages change would create a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Persist on every message change. We skip the trivial single-greeting
  // state so navigating to the page without typing anything doesn't write
  // an empty conversation to storage.
  useEffect(() => {
    if (!storageKey) return;
    const isInitialOnly =
      messages.length === 1 && messages[0]?.id === INITIAL_MESSAGE.id;
    if (isInitialOnly) return;
    savePersistedMessages(storageKey, messages);
  }, [messages, storageKey]);

  // Auto-scroll to the newest message whenever the message list grows.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const viewport =
      node.querySelector?.('[data-radix-scroll-area-viewport]') || node;
    viewport.scrollTop = viewport.scrollHeight;
  }, [messages, isTyping]);

  // One-shot legacy-key sweep: any pre-v2 entries are removed on mount so
  // older broken history (which persisted timeout error bubbles) can never
  // resurface even if logout never ran.
  useEffect(() => {
    purgeLegacyAssistantSessions();
  }, []);

  // Cancel any pending request when the component unmounts (page navigation).
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []);

  const sendMessage = useCallback(
    async (text) => {
      const trimmed = (text ?? '').trim();
      if (!trimmed || isTyping) return;

      // Abort any leftover controller from a previous (already-finished)
      // call before starting a fresh one. Belt-and-suspenders: the finally
      // block already nulls abortRef when the previous call ends, but if a
      // pathological race ever leaves one behind, this guarantees the new
      // call gets its own clean controller and signal.
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {
          /* noop */
        }
        abortRef.current = null;
      }

      const userMessage = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: trimmed,
      };
      setMessages((prev) => [...prev, userMessage]);
      setInputValue('');
      setIsTyping(true);

      const controller = new AbortController();
      abortRef.current = controller;
      const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      const t0 = Date.now();
      // eslint-disable-next-line no-console
      console.log('[assistant ui] sending', { len: trimmed.length });

      try {
        const result = await api.assistant.chat(trimmed, {
          signal: controller.signal,
          policy_id: policyScope !== 'all' ? policyScope : undefined,
        });

        const answer =
          (typeof result?.answer === 'string' && result.answer.trim()) ||
          (typeof result?.response === 'string' && result.response.trim()) ||
          "I couldn't generate a response. Please try rephrasing your question.";

        setContextSummary({
          hasPolicies: !!result?.has_policies,
          hasData: !!result?.has_data,
          policiesInScope: result?.policies_in_scope ?? 0,
        });

        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: answer,
            type: result?.has_data ? 'grounded' : 'no-data',
            sources: Array.isArray(result?.sources) ? result.sources : [],
          },
        ]);
        // eslint-disable-next-line no-console
        console.log('[assistant ui] answered', {
          ms: Date.now() - t0,
          has_data: !!result?.has_data,
        });
      } catch (error) {
        const isAbort =
          error?.name === 'AbortError' ||
          /aborted/i.test(error?.message || '');
        const raw = typeof error?.message === 'string' ? error.message : '';
        const friendly = isAbort
          ? 'The request took too long. Please try again with a simpler question.'
          : raw && raw.length > 0 && raw.length < 240
          ? raw
          : 'The assistant is temporarily unavailable. Please try again.';

        setMessages((prev) => [
          ...prev,
          {
            id: `e-${Date.now()}`,
            role: 'assistant',
            content: friendly,
            type: 'error',
          },
        ]);
        // eslint-disable-next-line no-console
        console.log('[assistant ui] error', {
          ms: Date.now() - t0,
          aborted: isAbort,
          msg: raw?.slice?.(0, 120),
        });
      } finally {
        clearTimeout(timer);
        if (abortRef.current === controller) abortRef.current = null;
        setIsTyping(false);
        inputRef.current?.focus();
      }
    },
    [isTyping, policyScope]
  );

  const handleSend = () => sendMessage(inputValue);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleReset = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setMessages([INITIAL_MESSAGE]);
    setInputValue('');
    setContextSummary(null);
    setIsTyping(false);
    clearPersistedMessages(storageKey);
    inputRef.current?.focus();
  };

  const showSuggestions = messages.length === 1 && !isTyping;

  return (
    <PageContainer
      title="AI Assistant"
      subtitle="Ask about your compliance status, gaps, and remediation — grounded in your real data"
      actions={
        <div className="flex items-center gap-2 flex-wrap">
          {/* Phase F: policy scope picker. Defaults to "All my policies"; pick
              one to scope the chatbot to a single document for tighter answers
              with [Page N · ¶M] citations. */}
          <Select value={policyScope} onValueChange={setPolicyScope}>
            <SelectTrigger className="w-[220px]" disabled={isTyping}>
              <FileText className="w-4 h-4 mr-1 shrink-0" />
              <SelectValue placeholder="All my policies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All my policies</SelectItem>
              {policies.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.file_name || p.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Badge className="bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30 gap-1">
            <Sparkles className="w-3 h-3" />
            AI Powered
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={messages.length <= 1 && !isTyping}
            title="Clear conversation"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Reset
          </Button>
        </div>
      }
    >
      <div className="max-w-4xl mx-auto">
        {contextSummary && <ContextStrip summary={contextSummary} />}

        <Card className="shadow-sm overflow-hidden">
          {/* Chat Messages */}
          <ScrollArea className="h-[500px] p-6" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}

              {isTyping && (
                <div className="flex gap-3">
                  <Avatar className="h-8 w-8 bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0">
                    <AvatarFallback className="bg-transparent">
                      <Bot className="w-4 h-4 text-white" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="bg-muted text-muted-foreground rounded-2xl px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="text-sm">
                        Reading your compliance data…
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Suggested Questions */}
          {showSuggestions && (
            <div className="px-6 py-3 border-t border-border bg-muted/40">
              <p className="text-xs font-medium text-muted-foreground mb-2">
                Try one of these:
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <Button
                    key={q}
                    variant="outline"
                    size="sm"
                    onClick={() => sendMessage(q)}
                    disabled={isTyping}
                    className="text-xs h-7"
                  >
                    {q}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="p-4 border-t border-border bg-card">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                placeholder="Ask about your compliance status, gaps, or what to fix first…"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isTyping}
                className="flex-1"
                aria-label="Message"
              />
              {/* Phase F: while a request is in flight, swap Send for Stop.
                  Aborting hits the AbortController, which the existing catch
                  block handles as a friendly "took too long" message. */}
              {isTyping ? (
                <Button
                  onClick={() => abortRef.current?.abort()}
                  variant="outline"
                  className="border-red-500/40 text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
                  aria-label="Stop generating"
                  title="Stop generating"
                >
                  <StopCircle className="w-4 h-4 mr-1.5" />
                  Stop
                </Button>
              ) : (
                <Button
                  onClick={handleSend}
                  disabled={!inputValue.trim()}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2 text-center">
              Answers are based on your stored policies and analyses. For
              complex decisions, consult your compliance team.
            </p>
          </div>
        </Card>
      </div>
    </PageContainer>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isError = message.type === 'error';
  const sources = Array.isArray(message.sources) ? message.sources : [];

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <Avatar className="h-8 w-8 bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0">
          <AvatarFallback className="bg-transparent">
            <Bot className="w-4 h-4 text-white" />
          </AvatarFallback>
        </Avatar>
      )}

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-emerald-600 text-white dark:bg-emerald-500'
            : isError
            ? 'bg-red-50 text-red-800 border border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/30'
            : 'bg-muted text-foreground'
        }`}
      >
        {!isUser && isError && (
          <div className="flex items-center gap-1.5 mb-1.5 text-xs font-medium">
            <AlertTriangle className="w-3.5 h-3.5" />
            Error
          </div>
        )}
        <div
          className={`text-sm prose prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 ${
            isUser ? 'prose-invert' : 'dark:prose-invert'
          }`}
        >
          <ReactMarkdown
            components={{
              // Phase F: any text-bearing slot runs through withCitations so
              // [Page N] tags become emerald pill chips wherever they appear.
              p: ({ children }) => <p className="mb-2 last:mb-0">{withCitations(children)}</p>,
              ul: ({ children }) => (
                <ul className="my-2 ml-4 list-disc">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="my-2 ml-4 list-decimal">{children}</ol>
              ),
              li: ({ children }) => <li className="mb-1">{withCitations(children)}</li>,
              strong: ({ children }) => (
                <strong className="font-semibold">{withCitations(children)}</strong>
              ),
              code: ({ children }) => (
                <code className="rounded bg-background/40 px-1 py-0.5 text-[0.85em]">
                  {children}
                </code>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {!isUser && !isError && sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {sources.slice(0, 6).map((s, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                title={`${s.framework || ''} ${s.control || ''} (${s.severity || ''})`}
              >
                <Database className="w-2.5 h-2.5" />
                {s.framework ? `${s.framework} · ` : ''}
                {s.control || 'Source'}
              </span>
            ))}
          </div>
        )}
      </div>

      {isUser && (
        <Avatar className="h-8 w-8 bg-muted flex-shrink-0">
          <AvatarFallback>
            <User className="w-4 h-4 text-muted-foreground" />
          </AvatarFallback>
        </Avatar>
      )}
    </div>
  );
}

function ContextStrip({ summary }) {
  const { hasPolicies, hasData, policiesInScope } = summary;

  let text;
  let tone;
  if (!hasPolicies) {
    text =
      'No policies uploaded yet — upload one and run analysis for grounded answers.';
    tone = 'warn';
  } else if (!hasData) {
    text = `${policiesInScope} polic${
      policiesInScope === 1 ? 'y' : 'ies'
    } on file, but no completed analysis yet — run analysis to unlock gap-level answers.`;
    tone = 'warn';
  } else {
    text = `Based on your latest analysis across ${policiesInScope} polic${
      policiesInScope === 1 ? 'y' : 'ies'
    }.`;
    tone = 'ok';
  }

  return (
    <div
      className={`mb-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        tone === 'ok'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
          : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'
      }`}
    >
      <Database className="w-3 h-3" />
      {text}
    </div>
  );
}
