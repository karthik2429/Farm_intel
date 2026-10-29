import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Send, Bot, User, Loader2, AlertTriangle } from 'lucide-react';
import BottomNav from '@/components/BottomNav';
import { getAiReply } from '@/lib/marketApi';

const AIChatPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Real district context: profile first, so replies are location-grounded.
  const district = localStorage.getItem('profile_district') || '';
  const state = localStorage.getItem('profile_state') || '';
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([
    {
      role: 'assistant',
      content: `${t('namaste')}! ${t('howCanIHelp')}`,
    },
  ]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, sending]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    const userMsg = { role: 'user' as const, content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setSending(true);
    setError(null);
    try {
      const data = await getAiReply(
        history.slice(-11).map((m) => ({ role: m.role, content: m.content })),
        district, state,
      );
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
    } catch (err: any) {
      setError(err?.message || 'Assistant unavailable right now');
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'I could not reach the assistant service just now. Please try again in a moment.',
      }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3 border-b border-border/50">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <div className="w-8 h-8 rounded-full gradient-primary flex items-center justify-center">
          <Bot className="w-4 h-4 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-sm font-extrabold text-foreground">{t('appName')} •</h1>
          <p className="text-[10px] text-muted-foreground">{t('aiAssistant')}</p>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3 pb-32">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full gradient-primary flex items-center justify-center flex-shrink-0 mt-1">
                <Bot className="w-3.5 h-3.5 text-primary-foreground" />
              </div>
            )}
            <div
              className={`max-w-[75%] px-3 py-2.5 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'gradient-primary text-primary-foreground rounded-br-md'
                  : 'glass-card text-foreground rounded-bl-md'
              }`}
            >
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-secondary flex items-center justify-center flex-shrink-0 mt-1">
                <User className="w-3.5 h-3.5 text-foreground" />
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="flex gap-2 justify-start">
            <div className="w-7 h-7 rounded-full gradient-primary flex items-center justify-center flex-shrink-0 mt-1">
              <Loader2 className="w-3.5 h-3.5 text-primary-foreground animate-spin" />
            </div>
            <div className="glass-card px-3 py-2.5 rounded-2xl text-sm text-muted-foreground">
              Thinking…
            </div>
          </div>
        )}
        {error && (
          <div className="glass-card px-3 py-2.5 rounded-2xl text-xs text-destructive/90 flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="fixed bottom-16 left-0 right-0 px-4 pb-3 bg-background/80 backdrop-blur-lg border-t border-border/30">
        <div className="flex items-center gap-2 bg-secondary rounded-2xl px-3 py-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder={sending ? 'Assistant is thinking…' : t('typeMessage')}
            disabled={sending}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60"
          />
          <button
            onClick={send}
            disabled={!input.trim() || sending}
            className="w-8 h-8 rounded-full gradient-primary flex items-center justify-center disabled:opacity-40 transition-opacity"
          >
            {sending
              ? <Loader2 className="w-4 h-4 text-primary-foreground animate-spin" />
              : <Send className="w-4 h-4 text-primary-foreground" />}
          </button>
        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default AIChatPage;
