// AI Chat Component for Macro Terminal
// Floating chat widget for asking the macro research assistant

import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, X, Bot, User } from 'lucide-react';
import { api } from '@/api/client';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export function AIChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');
    setError(null);

    // Add user message
    const userMessage: Message = {
      role: 'user',
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await api.post('/api/ask', { question });
      const assistantMessage: Message = {
        role: 'assistant',
        content: response.data.answer || 'No response received.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to get response. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuickQuestion = (question: string) => {
    setInput(question);
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-4 py-3 bg-accent text-bg font-medium rounded-lg shadow-lg hover:bg-accent/90 transition-colors"
      >
        <MessageSquare className="w-5 h-5" />
        <span className="text-sm">Ask the Terminal</span>
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-w-[calc(100vw-2rem)] bg-surface-1 border border-border shadow-2xl rounded-lg flex flex-col max-h-[600px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-surface-2 border-b border-border-subtle rounded-t-lg">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-accent" />
          <div>
            <h3 className="text-sm font-medium text-text-primary">Macro Assistant</h3>
            <p className="text-2xs text-text-tertiary">Ask about current conditions</p>
          </div>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1 hover:bg-surface-3 rounded transition-colors"
        >
          <X className="w-4 h-4 text-text-secondary" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[300px] max-h-[400px]">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-xs text-text-secondary text-center py-4">
              Ask about macro conditions, regime implications, or portfolio positioning.
            </p>
            <div className="space-y-2">
              <p className="text-2xs text-text-tertiary uppercase">Quick questions:</p>
              {[
                'What does stagflation mean for my bond exposure?',
                'Should I increase equity risk right now?',
                'Explain the current recession risk',
                'Which sectors are favored in this regime?',
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => handleQuickQuestion(q)}
                  className="w-full text-left px-3 py-2 text-xs text-text-secondary hover:bg-surface-2 hover:text-text-primary rounded transition-colors border border-border-subtle"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex gap-2 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
              message.role === 'user' ? 'bg-accent text-bg' : 'bg-surface-3 text-accent'
            }`}>
              {message.role === 'user' ? (
                <User className="w-3 h-3" />
              ) : (
                <Bot className="w-3 h-3" />
              )}
            </div>
            <div className={`max-w-[80%] px-3 py-2 rounded-lg text-xs ${
              message.role === 'user'
                ? 'bg-accent text-bg'
                : 'bg-surface-2 text-text-primary border border-border-subtle'
            }`}>
              {message.content}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-2">
            <div className="w-6 h-6 rounded-full bg-surface-3 text-accent flex items-center justify-center flex-shrink-0">
              <Bot className="w-3 h-3" />
            </div>
            <div className="px-3 py-2 bg-surface-2 border border-border-subtle rounded-lg">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-text-secondary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-text-secondary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-text-secondary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="px-3 py-2 bg-red/10 border border-red/30 rounded-lg text-xs text-red">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-border-subtle">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about macro conditions..."
            className="flex-1 px-3 py-2 bg-surface-2 border border-border-subtle rounded text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-3 py-2 bg-accent text-bg rounded hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
