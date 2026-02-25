import React, { useState, useRef, useEffect } from 'react';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  MessageSquare,
  Send,
  Bot,
  User,
  Sparkles,
  FileText,
  Shield,
  AlertTriangle,
  Loader2,
  RefreshCw
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';


export default function AIAssistant() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: "Hello! I'm your AI Compliance Assistant for Hemaya. I can help you understand your compliance status, explain control mappings, suggest improvements, and answer questions about NCA ECC, ISO 27001, and NIST 800-53 frameworks.\n\nHow can I assist you today?",
      type: 'greeting'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue.trim()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    try {
      // Call backend function
      const result = await api.functions.invoke('chat_assistant', {
        message: userMessage.content,
      });

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: result.response || 'Sorry, I encountered an error. Please try again.',
        type: 'info'
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again.',
        type: 'warning'
      };
      setMessages(prev => [...prev, errorMessage]);
    }

    setIsTyping(false);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestedQuestions = [
    "What's my current compliance status?",
    "What are my critical gaps?",
    "How can I improve my NCA ECC score?",
    "Explain ISO 27001 requirements",
  ];

  const getMessageIcon = (type) => {
    switch (type) {
      case 'success': return <Shield className="w-4 h-4 text-emerald-500" />;
      case 'warning': return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case 'suggestion': return <Sparkles className="w-4 h-4 text-purple-500" />;
      default: return <FileText className="w-4 h-4 text-blue-500" />;
    }
  };

  return (
    <PageContainer
      title="AI Assistant"
      subtitle="Get intelligent answers about your compliance posture"
      actions={
        <Badge className="bg-purple-100 text-purple-700 border-purple-200 gap-1">
          <Sparkles className="w-3 h-3" />
          AI Powered
        </Badge>
      }
    >
      <div className="max-w-4xl mx-auto">
        <Card className="shadow-sm overflow-hidden">
          {/* Chat Messages */}
          <ScrollArea className="h-[500px] p-6" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((message) => (
                <div 
                  key={message.id}
                  className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {message.role === 'assistant' && (
                    <Avatar className="h-8 w-8 bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0">
                      <AvatarFallback className="bg-transparent">
                        <Bot className="w-4 h-4 text-white" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                  
                  <div 
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      message.role === 'user' 
                        ? 'bg-slate-900 text-white' 
                        : 'bg-slate-100 text-slate-900'
                    }`}
                  >
                    {message.role === 'assistant' && message.type && message.type !== 'greeting' && (
                      <div className="flex items-center gap-1 mb-2">
                        {getMessageIcon(message.type)}
                        <span className="text-xs font-medium text-slate-500 capitalize">{message.type}</span>
                      </div>
                    )}
                    <div className="text-sm prose prose-sm prose-slate max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                          ul: ({ children }) => <ul className="my-2 ml-4 list-disc">{children}</ul>,
                          ol: ({ children }) => <ol className="my-2 ml-4 list-decimal">{children}</ol>,
                          li: ({ children }) => <li className="mb-1">{children}</li>,
                          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {message.role === 'user' && (
                    <Avatar className="h-8 w-8 bg-slate-200 flex-shrink-0">
                      <AvatarFallback>
                        <User className="w-4 h-4 text-slate-600" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              ))}
              
              {isTyping && (
                <div className="flex gap-3">
                  <Avatar className="h-8 w-8 bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0">
                    <AvatarFallback className="bg-transparent">
                      <Bot className="w-4 h-4 text-white" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="bg-slate-100 rounded-2xl px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-slate-500" />
                      <span className="text-sm text-slate-500">Thinking...</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Suggested Questions */}
          {messages.length <= 2 && (
            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50">
              <p className="text-xs font-medium text-slate-500 mb-2">Suggested questions:</p>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((question, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setInputValue(question);
                      inputRef.current?.focus();
                    }}
                    className="text-xs h-7"
                  >
                    {question}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="p-4 border-t border-slate-200 bg-white">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                placeholder="Ask me anything about your compliance..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isTyping}
                className="flex-1"
              />
              <Button 
                onClick={handleSend}
                disabled={!inputValue.trim() || isTyping}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-xs text-slate-400 mt-2 text-center">
              AI responses are based on your compliance data. For complex queries, consult with your compliance team.
            </p>
          </div>
        </Card>
      </div>
    </PageContainer>
  );
}