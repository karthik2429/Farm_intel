import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Send, Bot, User, Mic, Camera, Image } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

const AIChatPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([
    {
      role: 'assistant',
      content: `${t('namaste')}! ${t('howCanIHelp')}`,
    },
  ]);

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = { role: 'user' as const, content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    // Simulate AI response (you'll connect your own model)
    setTimeout(() => {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant' as const,
          content: 'This is a placeholder response. Connect your AI model backend to get real responses here.',
        },
      ]);
    }, 1000);
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
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 pb-32">
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
      </div>

      {/* Input */}
      <div className="fixed bottom-16 left-0 right-0 px-4 pb-3 bg-background/80 backdrop-blur-lg border-t border-border/30">
        <div className="flex items-center gap-2 bg-secondary rounded-2xl px-3 py-2">
          <button className="text-muted-foreground hover:text-foreground transition">
            <Camera className="w-5 h-5" />
          </button>
          <button className="text-muted-foreground hover:text-foreground transition">
            <Image className="w-5 h-5" />
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder={t('typeMessage')}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          <button className="text-muted-foreground hover:text-foreground transition">
            <Mic className="w-5 h-5" />
          </button>
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="w-8 h-8 rounded-full gradient-primary flex items-center justify-center disabled:opacity-40 transition-opacity"
          >
            <Send className="w-4 h-4 text-primary-foreground" />
          </button>
        </div>
      </div>

      <BottomNav />
    </div>
  );
};

export default AIChatPage;
