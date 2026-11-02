import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Camera,
  ExternalLink,
  Loader2,
  Mic,
  Send,
  Sparkles,
  Square,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { AppShell } from '@/components/ui-kit/AppShell';
import { Badge, Card, EmptyState, PriceSourceBadge } from '@/components/ui-kit/core';
import { Sparkline } from '@/components/ui-kit/core';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useProfile, defaultLocation } from '@/lib/profile';
import { speechLocale, languageNames } from '@/lib/i18n';
import { env } from '@/lib/env';
import { cn } from '@/lib/utils';

interface PriceCardData {
  commodity: string;
  price: number | null;
  unit?: string;
  market?: string | null;
  district?: string | null;
  date?: string | null;
  source?: string | null;
  is_real?: boolean | null;
  min_price?: number | null;
  max_price?: number | null;
}

interface ForecastCardData {
  commodity: string;
  current_price: number;
  predicted_change_pct: number;
  mape?: number;
  trajectory: { date: string; predicted_price: number }[];
}

interface Action {
  type: 'navigate' | 'open_external';
  url: string;
  label?: string;
  needs_confirmation?: boolean;
  auto?: boolean;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  cards?: { type: 'price' | 'forecast'; data: PriceCardData | ForecastCardData }[];
  actions?: Action[];
  source?: string;
  setup?: boolean;
}

const QUICK = {
  en: ['Tomato price in Kolar', '14-day onion forecast', 'Which crop should I sow?', 'Government schemes'],
  hi: ['कोलार में टमाटर का भाव', 'प्याज़ का 14 दिन का अनुमान', 'कौन सी फसल बोऊँ?', 'सरकारी योजनाएँ'],
  kn: ['ಕೋಲಾರದಲ್ಲಿ ಟೊಮೆಟೊ ಬೆಲೆ', 'ಈರುಳ್ಳಿ 14 ದಿನದ ಮುನ್ಸೂಚನೆ', 'ಯಾವ ಬೆಳೆ ಬೆಳೆಯಬೇಕು?', 'ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು'],
  te: ['కోలార్‌లో టొమాటో ధర', 'ఉల్లిపాయ 14 రోజుల అంచనా', 'ఏ పంట వేయాలి?', 'ప్రభుత్వ పథకాలు'],
  ta: ['கோலாரில் தக்காளி விலை', 'வெங்காயம் 14 நாள் முன்னறிவிப்பு', 'எந்த பயிர் விதைக்க?', 'அரசு திட்டங்கள்'],
  ml: ['കോലാറിൽ തക്കാളി വില', 'സവാള 14 ദിവസ പ്രവചനം', 'ഏത് വിള വിതയ്ക്കണം?', 'സർക്കാർ പദ്ധതികൾ'],
  mr: ['कोलारमध्ये टोमॅटोचा भाव', 'कांद्याचा 14 दिवसांचा अंदाज', 'कोणते पीक पेरू?', 'सरकारी योजना'],
  gu: ['કોલારમાં ટામેટાનો ભાવ', 'ડુંગળી 14 દિવસનું અનુમાન', 'કયો પાક વાવું?', 'સરકારી યોજનાઓ'],
  bn: ['কোলারে টমেটোর দাম', 'পেঁয়াজ ১৪ দিনের পূর্বাভাস', 'কোন ফসল বুনব?', 'সরকারি প্রকল্প'],
  pa: ['ਕੋਲਾਰ ਵਿੱਚ ਟਮਾਟਰ ਦਾ ਭਾਅ', 'ਪਿਆਜ਼ 14 ਦਿਨਾਂ ਦਾ ਅੰਦਾਜ਼ਾ', 'ਕਿਹੜੀ ਫ਼ਸਲ ਬੀਜਾਂ?', 'ਸਰਕਾਰੀ ਯੋਜਨਾਵਾਂ'],
  or: ['କୋଲାରରେ ଟମାଟୋ ଦର', 'ପିଆଜ ୧୪ ଦିନର ପୂର୍ବାନୁମାନ', 'କେଉଁ ଫସଲ ବୁଣିବି?', 'ସରକାରୀ ଯୋଜନା'],
};

const ChatPage: React.FC = () => {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { profile } = useProfile(user?.id, user?.email);
  const loc = defaultLocation(profile);

  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [listening, setListening] = React.useState(false);
  const [speakingId, setSpeakingId] = React.useState<string | null>(null);
  const [micSupported, setMicSupported] = React.useState(false);
  const [ttsSupported, setTtsSupported] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const recognitionRef = React.useRef<any>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    setMicSupported(Boolean(SR));
    setTtsSupported(typeof window !== 'undefined' && 'speechSynthesis' in window);
  }, []);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, busy]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const userMsg: Message = { id: `u${Date.now()}`, role: 'user', text: question };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setBusy(true);

    try {
      const res = await fetch(`${env.apiBaseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.text })),
          district: loc.district || null,
          state: loc.state || null,
          lang: language,
          user_id: user?.id || null,
          name: profile?.name || null,
          crops: profile?.crops || [],
          season: profile?.season_focus || 'kharif',
          land_size: profile?.land_size ?? null,
          land_unit: profile?.land_unit || null,
          soil: profile?.soil || null,
        }),
      });

      if (res.status === 429) {
        const body = await res.json().catch(() => ({}));
        setMessages((m) => [
          ...m,
          {
            id: `a${Date.now()}`,
            role: 'assistant',
            text: body?.detail || 'You are sending messages too fast. Please try again in a minute.',
          },
        ]);
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setMessages((m) => [
          ...m,
          {
            id: `a${Date.now()}`,
            role: 'assistant',
            text: body?.detail || 'The assistant is not reachable right now.',
          },
        ]);
        return;
      }

      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          id: `a${Date.now()}`,
          role: 'assistant',
          text: data.reply,
          cards: data.cards || [],
          actions: data.actions || [],
          source: data.source,
          setup: data.source === 'setup' || Boolean(data.setup_required),
        },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        {
          id: `a${Date.now()}`,
          role: 'assistant',
          text: 'I could not reach the backend. Start it with ./start.sh and try again.',
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const startListening = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    recognitionRef.current = rec;
    rec.lang = speechLocale[language];
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e: any) => {
      const said = e.results?.[0]?.[0]?.transcript;
      if (said) void send(said);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    setListening(true);
    rec.start();
  };

  const stopListening = () => {
    recognitionRef.current?.stop?.();
    setListening(false);
  };

  const speak = (m: Message) => {
    if (!ttsSupported) return;
    if (speakingId === m.id) {
      window.speechSynthesis.cancel();
      setSpeakingId(null);
      return;
    }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(m.text);
    utter.lang = speechLocale[language];
    utter.onend = () => setSpeakingId(null);
    utter.onerror = () => setSpeakingId(null);
    setSpeakingId(m.id);
    window.speechSynthesis.speak(utter);
  };

  const onPhoto = async (file: File) => {
    if (file.size > 1_000_000) {
      setMessages((m) => [
        ...m,
        { id: `a${Date.now()}`, role: 'assistant', text: 'That photo is over 1 MB. Please pick a smaller one so it uploads quickly.' },
      ]);
      return;
    }
    setMessages((m) => [
      ...m,
      {
        id: `a${Date.now()}`,
        role: 'assistant',
        text:
          'Leaf-photo analysis runs on Gemini vision and needs GEMINI_API_KEY configured on the ' +
          'backend. Until then I can only read your text questions. AI suggestion — not a lab diagnosis.',
        setup: true,
      },
    ]);
  };

  const quick = QUICK[language] || QUICK.en;

  return (
    <AppShell>
      <div className="flex min-h-[calc(100vh-9rem)] flex-col">
        <div className="sticky top-0 z-20 -mx-4 mb-3 flex items-center gap-2 border-b border-border bg-background/85 px-4 py-2.5 backdrop-blur-xl sm:-mx-6 sm:px-6">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-hero text-white shadow-glow">
            <Sparkles className="h-4 w-4" strokeWidth={2} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-[15px] font-800 leading-tight">{t('aiAssistant')}</p>
            <p className="truncate text-[11px] text-ink-muted">
              {languageNames[language]} · {loc.label || 'All India'}
            </p>
          </div>
          <LanguageSwitcher compact />
        </div>

        <div className="flex-1 space-y-3 pb-4">
          {!messages.length && (
            <Card className="text-center">
              <div className="mx-auto mb-2 grid h-12 w-12 place-items-center rounded-full bg-primary/12 text-primary">
                <Sparkles className="h-5 w-5" strokeWidth={2} />
              </div>
              <p className="font-display text-[15px] font-700">{t('howCanIHelp')}</p>
              <p className="mx-auto mt-1 max-w-[36ch] text-[12px] leading-relaxed text-ink-muted">
                Ask about mandi prices, 14-day forecasts, which crop to sow, fertiliser or
                government schemes. Prices come from the real mandi database.
              </p>
            </Card>
          )}

          {messages.map((m) => (
            <div key={m.id} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className={cn('max-w-[85%] space-y-2', m.role === 'user' && 'items-end')}>
                <div
                  className={cn(
                    'rounded-md px-3.5 py-2.5 text-[13.5px] leading-relaxed shadow-sm',
                    m.role === 'user'
                      ? 'rounded-br-sm bg-hero text-white'
                      : 'rounded-bl-sm border border-border bg-surface text-ink',
                  )}
                >
                  {m.text}
                </div>

                {m.cards?.map((c, i) =>
                  c.type === 'price' ? (
                    <PriceBubble key={i} data={c.data as PriceCardData} onOpen={() => navigate(`/predict?crop=${encodeURIComponent((c.data as PriceCardData).commodity)}`)} />
                  ) : (
                    <ForecastBubble key={i} data={c.data as ForecastCardData} onOpen={() => navigate(`/predict?crop=${encodeURIComponent((c.data as ForecastCardData).commodity)}`)} />
                  ),
                )}

                {m.actions?.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {m.actions.map((a, i) =>
                      a.type === 'navigate' ? (
                        <button
                          key={i}
                          type="button"
                          onClick={() => navigate(a.url)}
                          className="press rounded-full bg-primary px-3 py-1.5 text-[11.5px] font-700 text-primary-foreground"
                        >
                          {a.label || 'Open'}
                        </button>
                      ) : (
                        <button
                          key={i}
                          type="button"
                          onClick={() => {
                            if (a.needs_confirmation && !window.confirm(`Open ${a.url}?`)) return;
                            window.open(a.url, '_blank', 'noopener,noreferrer');
                          }}
                          className="press inline-flex items-center gap-1 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-600"
                        >
                          {a.label || a.url}
                          <ExternalLink className="h-3 w-3" strokeWidth={2.2} />
                        </button>
                      ),
                    )}
                  </div>
                ) : null}

                {m.role === 'assistant' && ttsSupported && (
                  <button
                    type="button"
                    onClick={() => speak(m)}
                    className="inline-flex items-center gap-1 text-[10.5px] font-600 text-ink-muted hover:text-primary"
                  >
                    {speakingId === m.id ? (
                      <>
                        <VolumeX className="h-3 w-3" strokeWidth={2.2} /> {t('stopSpeaking')}
                      </>
                    ) : (
                      <>
                        <Volume2 className="h-3 w-3" strokeWidth={2.2} /> {t('speakReply')}
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="flex items-center gap-1.5 rounded-md rounded-bl-sm border border-border bg-surface px-3 py-2.5 w-fit">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-muted"
                  style={{ animationDelay: `${i * 120}ms` }}
                />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* quick replies */}
        {!messages.length && (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 no-scrollbar">
            {quick.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => void send(q)}
                className="press shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[11.5px] font-600 text-ink-muted hover:border-primary/40 hover:text-ink"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* input bar */}
        <div className="sticky bottom-20 z-20 md:bottom-2">
          <div className="flex items-end gap-1.5 rounded-lg border border-border bg-surface p-1.5 shadow-md">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              aria-label={t('attachPhoto')}
              className="press grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink-muted hover:bg-surface-2"
            >
              <Camera className="h-[18px] w-[18px]" strokeWidth={1.9} />
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onPhoto(f);
                e.target.value = '';
              }}
            />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              placeholder={t('typeMessage')}
              className="max-h-24 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-[14px] outline-none placeholder:text-ink-muted/70"
            />
            {micSupported ? (
              <button
                type="button"
                onClick={listening ? stopListening : startListening}
                aria-label={listening ? t('listening') : 'Speak'}
                className={cn(
                  'press grid h-10 w-10 shrink-0 place-items-center rounded-full',
                  listening ? 'bg-gold text-forest animate-pulse-soft' : 'bg-surface-2 text-ink-muted',
                )}
              >
                {listening ? <Square className="h-4 w-4" strokeWidth={2.4} /> : <Mic className="h-[18px] w-[18px]" strokeWidth={2} />}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void send(input)}
              disabled={!input.trim() || busy}
              aria-label="Send"
              className="press grid h-10 w-10 shrink-0 place-items-center rounded-full text-white disabled:opacity-40"
              style={{ background: 'var(--grad-leaf)' }}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" strokeWidth={2.2} />}
            </button>
          </div>
          <p className="mt-1 px-1 text-center text-[10px] text-ink-muted">
            {t('notALabDiagnosis')}
          </p>
        </div>
      </div>
    </AppShell>
  );
};

function PriceBubble({ data, onOpen }: { data: PriceCardData; onOpen: () => void }) {
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-display text-[13px] font-700">{data.commodity}</p>
          <p className="truncate text-[11px] text-ink-muted">
            {data.market || data.district || '—'} {data.date ? `· ${data.date}` : ''}
          </p>
        </div>
        <div className="text-right">
          <p className="font-display text-[20px] font-800 leading-none tnum">
            {data.price != null ? `₹${Number(data.price).toLocaleString('en-IN')}` : '--'}
          </p>
          <p className="text-[9.5px] uppercase tracking-wide text-ink-muted">per quintal</p>
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <PriceSourceBadge source={data.source} isReal={data.is_real} updatedAt={data.date} />
        <button type="button" onClick={onOpen} className="text-[11px] font-700 text-primary">
          14-day forecast →
        </button>
      </div>
    </Card>
  );
}

function ForecastBubble({ data, onOpen }: { data: ForecastCardData; onOpen: () => void }) {
  const up = data.predicted_change_pct >= 0;
  const spark = data.trajectory?.map((p) => p.predicted_price) || [];
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate font-display text-[13px] font-700">{data.commodity}</p>
        <Badge tone={up ? 'live' : 'danger'}>
          {up ? '+' : ''}
          {data.predicted_change_pct.toFixed(1)}% in 14d
        </Badge>
      </div>
      <div className="mt-1.5 flex items-end justify-between">
        <div>
          <p className="font-display text-[20px] font-800 leading-none tnum">
            ₹{Math.round(data.current_price).toLocaleString('en-IN')}
          </p>
          <p className="text-[9.5px] uppercase tracking-wide text-ink-muted">
            today · MAPE {data.mape?.toFixed(1) ?? '—'}%
          </p>
        </div>
        {spark.length > 1 && <Sparkline points={spark} width={90} height={26} positive={up} />}
      </div>
      <button type="button" onClick={onOpen} className="mt-2 text-[11px] font-700 text-primary">
        Open full forecast →
      </button>
    </Card>
  );
}

export default ChatPage;
