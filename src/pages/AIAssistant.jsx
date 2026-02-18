import React, { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
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

const Policy = base44.entities.Policy;
const ComplianceResult = base44.entities.ComplianceResult;
const Gap = base44.entities.Gap;

// Deterministic responses based on context
const generateResponse = (message, context) => {
  const lowerMessage = message.toLowerCase();
  const { policies, results, gaps } = context;

  // Policy-related questions
  if (lowerMessage.includes('policy') || lowerMessage.includes('policies')) {
    if (policies.length === 0) {
      return {
        text: "You haven't uploaded any policies yet. To get started, go to the **Policies** page and upload your first security policy document. I can help analyze it once it's uploaded!",
        type: 'info'
      };
    }
    const policyNames = policies.map(p => p.file_name).join(', ');
    return {
      text: `You currently have **${policies.length} policies** uploaded: ${policyNames}.\n\nWould you like me to:\n- Summarize the compliance status of a specific policy?\n- Suggest improvements for any policy?\n- Compare policies across frameworks?`,
      type: 'info'
    };
  }

  // Gap-related questions
  if (lowerMessage.includes('gap') || lowerMessage.includes('missing') || lowerMessage.includes('remediat')) {
    const openGaps = gaps.filter(g => g.status === 'Open');
    const criticalGaps = gaps.filter(g => g.severity === 'Critical');
    
    if (openGaps.length === 0) {
      return {
        text: "Great news! You currently have no open compliance gaps. Keep up the excellent work maintaining your security posture!",
        type: 'success'
      };
    }
    
    return {
      text: `You have **${openGaps.length} open gaps** that need attention${criticalGaps.length > 0 ? `, including **${criticalGaps.length} critical** ones` : ''}.\n\n**Priority recommendations:**\n1. Address critical gaps first, particularly those related to access control and data protection\n2. Assign owners to unassigned gaps\n3. Set realistic due dates for remediation\n\nWould you like specific remediation guidance for any particular gap?`,
      type: 'warning'
    };
  }

  // Compliance score questions
  if (lowerMessage.includes('score') || lowerMessage.includes('compliance') || lowerMessage.includes('status')) {
    if (results.length === 0) {
      return {
        text: "You haven't run any compliance analyses yet. Upload a policy and run an analysis to see your compliance scores across frameworks.",
        type: 'info'
      };
    }

    const latestByFramework = {};
    results.forEach(r => {
      if (!latestByFramework[r.framework] || new Date(r.analyzed_at) > new Date(latestByFramework[r.framework].analyzed_at)) {
        latestByFramework[r.framework] = r;
      }
    });

    const summaries = Object.values(latestByFramework).map(r => 
      `- **${r.framework}**: ${Math.round(r.compliance_score || 0)}% (${r.status})`
    ).join('\n');

    return {
      text: `Here's your current compliance status:\n\n${summaries}\n\n**Key insights:**\n- Focus on frameworks below 70% compliance\n- Review partial controls for quick wins\n- Address missing controls systematically`,
      type: 'info'
    };
  }

  // Improvement suggestions
  if (lowerMessage.includes('improve') || lowerMessage.includes('suggest') || lowerMessage.includes('recommend')) {
    return {
      text: `Based on your compliance data, here are my **top recommendations**:\n\n1. **Access Control Enhancements** - Implement role-based access control (RBAC) and regular access reviews\n\n2. **Documentation Updates** - Ensure policies explicitly reference control requirements\n\n3. **Monitoring & Logging** - Establish comprehensive security event logging\n\n4. **Training Programs** - Develop role-specific security awareness training\n\n5. **Incident Response** - Document and test your incident response procedures\n\nWould you like detailed guidance on any of these areas?`,
      type: 'suggestion'
    };
  }

  // Framework-specific questions
  if (lowerMessage.includes('nca') || lowerMessage.includes('ecc')) {
    return {
      text: `**NCA ECC (Essential Cybersecurity Controls)** is Saudi Arabia's national cybersecurity framework.\n\n**Key domains:**\n- Cybersecurity Governance\n- Cybersecurity Defense\n- Cybersecurity Resilience\n- Third-Party & Cloud Cybersecurity\n- ICS Cybersecurity\n\nTo improve your NCA ECC compliance, focus on:\n1. Establishing a cybersecurity committee\n2. Implementing security baselines\n3. Conducting regular risk assessments\n4. Developing incident response capabilities`,
      type: 'info'
    };
  }

  if (lowerMessage.includes('iso') || lowerMessage.includes('27001')) {
    return {
      text: `**ISO 27001:2022** is the international standard for Information Security Management Systems (ISMS).\n\n**Key control domains:**\n- Organizational controls (A.5)\n- People controls (A.6)\n- Physical controls (A.7)\n- Technological controls (A.8)\n\nTo improve ISO 27001 compliance:\n1. Document your ISMS scope and policy\n2. Conduct risk assessment and treatment\n3. Implement Statement of Applicability (SoA)\n4. Establish internal audit program`,
      type: 'info'
    };
  }

  if (lowerMessage.includes('nist') || lowerMessage.includes('800-53')) {
    return {
      text: `**NIST 800-53 Rev. 5** provides security and privacy controls for federal information systems.\n\n**Control families include:**\n- Access Control (AC)\n- Audit and Accountability (AU)\n- Security Assessment (CA)\n- Configuration Management (CM)\n- Incident Response (IR)\n\nFor NIST 800-53 compliance:\n1. Categorize your systems (FIPS 199)\n2. Select baseline controls\n3. Implement and assess controls\n4. Authorize and monitor continuously`,
      type: 'info'
    };
  }

  // Help / what can you do
  if (lowerMessage.includes('help') || lowerMessage.includes('what can you') || lowerMessage.includes('how do i')) {
    return {
      text: `I'm your **AI Compliance Assistant**! I can help you with:\n\n📊 **Analysis & Insights**\n- Explain compliance scores and status\n- Identify priority gaps and risks\n- Suggest remediation actions\n\n📚 **Framework Guidance**\n- NCA ECC, ISO 27001, NIST 800-53 requirements\n- Control mapping explanations\n- Best practices for compliance\n\n📝 **Policy Support**\n- Review policy coverage\n- Suggest policy improvements\n- Explain control requirements\n\nJust ask me anything about your compliance posture!`,
      type: 'info'
    };
  }

  // Default response
  return {
    text: `I understand you're asking about "${message.substring(0, 50)}..."\n\nI can help you with:\n- **Compliance status** - Understanding your current scores\n- **Gap analysis** - Identifying and prioritizing gaps\n- **Framework guidance** - NCA ECC, ISO 27001, NIST requirements\n- **Policy improvements** - Suggestions to enhance compliance\n\nCould you please be more specific about what you'd like to know?`,
    type: 'info'
  };
};

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

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const { data: results = [] } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list(),
  });

  const { data: gaps = [] } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.list(),
  });

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
      const result = await base44.functions.invoke('chat_assistant', {
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