import React, { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '@/api/apiClient';
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
} from 'lucide-react';

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

export default function AIAssistant() {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [contextSummary, setContextSummary] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to the newest message whenever the message list grows.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    // Radix ScrollArea exposes a viewport child; fall back to the root.
    const viewport = node.querySelector?.('[data-radix-scroll-area-viewport]') || node;
    viewport.scrollTop = viewport.scrollHeight;
  }, [messages, isTyping]);

  const sendMessage = useCallback(async (text) => {
    const trimmed = (text ?? '').trim();
    if (!trimmed || isTyping) return;

    const userMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    try {
      const result = await api.functions.invoke('chat_assistant', {
        message: trimmed,
      });

      setContextSummary({
        hasPolicies: !!result?.has_policies,
        hasAnalysis: !!result?.has_analysis_data,
        policiesInScope: result?.policies_in_scope ?? 0,
      });

      const assistantMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content:
          (typeof result?.response === 'string' && result.response.trim()) ||
          "I couldn't generate a response. Please try rephrasing your question.",
        type: result?.has_analysis_data ? 'grounded' : 'no-data',
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      // The shared API client formats backend `detail` into error.message.
      // Keep it short to avoid leaking anything verbose.
      const raw = typeof error?.message === 'string' ? error.message : '';
      const friendly =
        raw && raw.length < 200
          ? raw
          : 'The assistant is temporarily unavailable. Please try again in a moment.';
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          content: friendly,
          type: 'error',
        },
      ]);
    } finally {
      setIsTyping(false);
      // Return focus to the input for fast follow-ups.
      inputRef.current?.focus();
    }
  }, [isTyping]);

  const handleSend = () => sendMessage(inputValue);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleReset = () => {
    setMessages([INITIAL_MESSAGE]);
    setInputValue('');
    setContextSummary(null);
    inputRef.current?.focus();
  };

  // Suggested chips show only at the start of a conversation.
  const showSuggestions = messages.length === 1 && !isTyping;

  return (
    <PageContainer
      title="AI Assistant"
      subtitle="Ask about your compliance status, gaps, and remediation — grounded in your real data"
      actions={
        <div className="flex items-center gap-2">
          <Badge className="bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30 gap-1">
            <Sparkles className="w-3 h-3" />
            AI Powered
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={messages.length <= 1 || isTyping}
            title="Clear conversation"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Reset
          </Button>
        </div>
      }
    >
      <div className="max-w-4xl mx-auto">
        {contextSummary && (
          <ContextStrip summary={contextSummary} />
        )}

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
                onKeyDown={handleKeyPress}
                disabled={isTyping}
                className="flex-1"
                aria-label="Message"
              />
              <Button
                onClick={handleSend}
                disabled={!inputValue.trim() || isTyping}
                className="bg-emerald-600 hover:bg-emerald-700"
                aria-label="Send message"
              >
                {isTyping ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </Button>
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
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => (
                <ul className="my-2 ml-4 list-disc">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="my-2 ml-4 list-decimal">{children}</ol>
              ),
              li: ({ children }) => <li className="mb-1">{children}</li>,
              strong: ({ children }) => (
                <strong className="font-semibold">{children}</strong>
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
  const { hasPolicies, hasAnalysis, policiesInScope } = summary;

  let text;
  let tone;
  if (!hasPolicies) {
    text = 'No policies uploaded yet — upload one and run analysis for grounded answers.';
    tone = 'warn';
  } else if (!hasAnalysis) {
    text = `${policiesInScope} polic${policiesInScope === 1 ? 'y' : 'ies'} on file, but no completed analysis yet — run analysis to unlock gap-level answers.`;
    tone = 'warn';
  } else {
    text = `Based on your latest analysis across ${policiesInScope} polic${policiesInScope === 1 ? 'y' : 'ies'}.`;
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
