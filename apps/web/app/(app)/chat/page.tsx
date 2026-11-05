"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Copy, Mic, Send, Sparkles, Square, X } from "@/components/ui/icons";
import { Drawer, ConfirmDialog } from "@/components/ui/overlays";
import { DraftActionCard } from "@/components/ui/DraftActionCard";
import { api } from "@/lib/api";

type Draft = { id: string; action_type: string; payload: Record<string, unknown>; status: string; result?: Record<string, unknown>; error?: string };
type Source = { type: string; label: string; url?: string; article?: string; excerpt?: string };
type Message = { id: string; role: string; content: string; agent?: string | null; sources?: Source[]; draft_actions?: Draft[]; created_at: string };
type Conversation = { id: string; title: string; updated_at: string; message_count: number };

const AGENT_LABELS: Record<string, string> = {
  orchestrator: "Orkestrator", document: "Hujjat agenti", reporting: "Hisobot agenti",
  legislation: "Qonunchilik agenti", credit_subsidy: "Kredit-subsidiya agenti", plan_control: "Reja va nazorat agenti",
};

const COMMANDS: Array<{ cmd: string; hint: string; build: (arg: string) => string }> = [
  { cmd: "/bugun", hint: "Bugungi vazifalar", build: () => "Bugun qaysi vazifalarga e’tibor berishim kerak?" },
  { cmd: "/kechikkan", hint: "Muddati o‘tgan vazifalar", build: () => "Muddatidan oshgan vazifalar va shoshilinch murojaatlarni ko‘rsat" },
  { cmd: "/vazifa", hint: "Vazifa loyihasi — /vazifa <matn>", build: (arg) => `vazifa yarat: ${arg || "Yangi topshiriq"}` },
  { cmd: "/hisobot", hint: "Hisobot — /hisobot [kunlik|haftalik|oylik]", build: (arg) => `${arg || "shu oy"} hisobot tayyorla` },
  { cmd: "/fuqaro", hint: "Fuqaro qidirish — /fuqaro <F.I.Sh.>", build: (arg) => `${arg} haqida ma’lumot ber` },
  { cmd: "/son", hint: "Aniq statistika — /son nogironligi bor fuqarolar", build: (arg) => arg || "Bazadagi fuqarolar soni nechta?" },
  { cmd: "/qonun", hint: "Qonunchilik — /qonun <savol>", build: (arg) => `qonun bo‘yicha: ${arg}` },
  { cmd: "/kredit", hint: "Kredit-subsidiya — /kredit <bank>", build: (arg) => (arg ? `${arg} krediti shartlari qanday?` : "Kredit olishni xohlayman") },
  { cmd: "/import", hint: "Import holati va xatoliklar", build: () => "Yuklagan faylimdagi xatoliklarni tahlil qilib ber" },
  { cmd: "/agentlar", hint: "Agentlar holati", build: () => "Agentlar holati qanday?" },
  { cmd: "/eksport", hint: "Eksport tartibi", build: () => "Eksport qilish tartibini tushuntir" },
];

type RecognitionLike = {
  lang: string; interimResults: boolean; continuous: boolean;
  start: () => void; stop: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [busySeconds, setBusySeconds] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [hl, setHl] = useState(0);

  const loadConversations = useCallback(() => {
    api.get<{ items: Conversation[] }>("/agents/conversations").then((d) => setConversations(d.items)).catch(() => {});
  }, []);

  const loadConversation = useCallback((id: string) => {
    setConversationId(id);
    api.get<{ messages: Message[] }>(`/agents/conversations/${id}`).then((d) => setMessages(d.messages)).catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  useEffect(() => { void loadConversations(); }, [loadConversations]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [messages, busy]);

  useEffect(() => {
    if (!busy) { setBusySeconds(0); return; }
    const timer = setInterval(() => setBusySeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "44px";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setWarning("");
    setInput("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: message, created_at: new Date().toISOString() }]);
    try {
      const result = await api.post<{ conversation_id: string; message: Message; warnings: string[] }>("/agents/chat", { message, conversation_id: conversationId });
      setConversationId(result.conversation_id);
      setMessages((prev) => [...prev, result.message]);
      if (result.warnings?.length) setWarning(result.warnings.join(" "));
      loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assistent javob bermadi.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(draft: Draft, approve: boolean) {
    try {
      await api.post(`/agents/drafts/${draft.id}/${approve ? "approve" : "reject"}`, { note: approve ? "Administrator tasdiqladi" : "Administrator rad etdi" });
      if (conversationId) loadConversation(conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Amal bajarilmadi.");
    }
  }

  async function removeConversation() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.del(`/agents/conversations/${deleteTarget.id}?purge=true`);
      setConversations((prev) => prev.filter((item) => item.id !== deleteTarget.id));
      if (conversationId === deleteTarget.id) { setConversationId(null); setMessages([]); }
      setDeleteTarget(null);
    } catch {
      setError("Suhbatni o‘chirish amalga oshmadi.");
      loadConversations();
    } finally {
      setDeleting(false);
    }
  }

  function toggleMic() {
    const w = window as unknown as { SpeechRecognition?: new () => RecognitionLike; webkitSpeechRecognition?: new () => RecognitionLike };
    const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Recognition) { setError("Brauzeringiz ovozli kiritishni qo‘llab-quvvatlamaydi (Chrome tavsiya etiladi)."); return; }
    if (listening) { recognitionRef.current?.stop(); setListening(false); return; }
    const recognition = new Recognition();
    recognition.lang = "uz-UZ";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i += 1) transcript += event.results[i][0].transcript;
      setInput((prev) => (prev ? `${prev} ${transcript.trim()}` : transcript.trim()));
    };
    recognition.onerror = (e) => {
      setListening(false);
      if (e.error === "not-allowed") setError("Mikrofon ruxsati berilmadi. Brauzer sozlamalaridan ruxsat bering.");
      else if (e.error === "no-speech") setError("Ovoz aniqlanmadi — qayta urinib ko‘ring.");
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  function copyMessage(message: Message) {
    void navigator.clipboard?.writeText(message.content);
    setCopied(message.id);
    setTimeout(() => setCopied(null), 1500);
  }

  const slashQuery = input.startsWith("/") ? input.slice(1).toLowerCase() : null;
  const matchedCommands = slashQuery === null ? [] : COMMANDS.filter((c) => c.cmd.slice(1).startsWith(slashQuery.split(" ")[0]));

  const historyList = (
    <>
      <button className="btn primary w-full mb" onClick={() => { setConversationId(null); setMessages([]); setHistoryOpen(false); }}>
        <Sparkles size={15} /> Yangi suhbat
      </button>
      {conversations.map((conversation) => (
        <div key={conversation.id} className="chat-history-item">
          <button
            className={`btn sm chat-history-btn ${conversationId === conversation.id ? "active" : ""}`}
            onClick={() => { loadConversation(conversation.id); setHistoryOpen(false); }}
            aria-current={conversationId === conversation.id ? "true" : undefined}
          >
            <span className="truncate">{conversation.title}</span>
          </button>
          <button className="icon-btn danger" aria-label={`${conversation.title} suhbatini o‘chirish`} title="O‘chirish" onClick={() => setDeleteTarget(conversation)}>
            <X size={14} />
          </button>
        </div>
      ))}
      {conversations.length === 0 && <p className="text-faint">Hozircha suhbat yo‘q.</p>}
    </>
  );

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">AI assistent · 5 agent + orkestrator</div>
          <h1>Suhbat</h1>
          <p className="lede">
            Xabar maydoniga <code>/</code> yozib tayyor buyruqlarni ko‘ring, <Mic size={13} /> tugmasi bilan gapiring.
            Javoblar manbali, yozuv amallari tasdiqingiz bilan bajariladi.
          </p>
        </div>
        <button className="btn sm mobile-only" onClick={() => setHistoryOpen(true)}>Suhbatlar</button>
      </div>

      {error && (
        <div className="alert danger" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}
      {warning && (
        <div className="alert warn" role="status">
          <AlertTriangle size={16} />
          <span>{warning}</span>
        </div>
      )}

      <div className="split s2r">
        <div className="card card-pad chat-history-panel hide-mobile">
          {historyList}
        </div>

        <div className="card card-pad">
          <span className="sr-only" aria-live="polite">
            {copied ? "Javob nusxalandi" : ""}
          </span>
          <div className="chat-wrap">
            <div className="chat-scroll" ref={scrollRef}>
              {messages.length === 0 && (
                <div className="empty">
                  <div className="icon"><Sparkles size={18} /></div>
                  <h3>Assistentga savol bering</h3>
                  <p>Xabar maydoniga <code>/</code> yozib tayyor buyruqlarni ko‘ring — yoki mikrofon bilan gapiring.</p>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`msg ${message.role === "user" ? "user" : "bot"}`}>
                  {message.role !== "user" && (
                    <div className="tag">
                      <span>{message.agent ? AGENT_LABELS[message.agent] ?? message.agent : "Assistent"}</span>
                      <button
                        className="chip chat-copy"
                        onClick={() => copyMessage(message)}
                        aria-label={copied === message.id ? "Javob nusxalandi" : "Javobni nusxalash"}
                        title={copied === message.id ? "Nusxalandi" : "Nusxalash"}
                      >
                        {copied === message.id ? (
                          <Check size={12} className="chat-copy-ok" aria-hidden="true" />
                        ) : (
                          <Copy size={12} aria-hidden="true" />
                        )}
                      </button>
                    </div>
                  )}
                  {message.role === "user" ? (
                    message.content
                  ) : (
                    <div className="md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}
                  {(message.sources ?? []).length > 0 && (
                    <div className="sources">
                      {message.sources!.slice(0, 5).map((source, index) => (
                        <div key={index}>
                          <span className="src-title">[{index + 1}] {source.label}</span>
                          {source.article && source.article !== "umumiy qoida" ? ` — ${source.article}` : ""}
                          {source.excerpt ? <div className="src-excerpt">{source.excerpt}</div> : null}
                          {source.url && (
                            <>
                              {" "}
                              <a className="link" href={source.url} target="_blank" rel="noreferrer">manba ↗</a>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {(message.draft_actions ?? []).map((draft) => (
                    <DraftActionCard key={draft.id} draft={draft} onDecide={(d, approve) => void decide(d, approve)} />
                  ))}
                </div>
              ))}
              {busy && (
                <div className="msg bot">
                  <div className="tag"><span>Orkestrator</span></div>
                  <span className="typing-dots" aria-label="Assistent javob tayyorlamoqda">
                    <i /><i /><i />
                  </span>
                  <span className="sr-only">Assistent javob tayyorlamoqda…</span>
                  <div className="chat-busy-note">
                    Kerakli agentlar ishga tushirilmoqda…
                    {busySeconds >= 10 && (
                      <div className="text-faint fs-12_5 mt-xs">
                        Ma’lumotlar bazasi va tashqi manbalar tekshirilmoqda — bu 1–2 daqiqa olishi mumkin.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            {matchedCommands.length > 0 && (
              <div className="slash-panel" role="listbox" aria-label="Buyruqlar">
                {matchedCommands.map((command, i) => (
                  <button
                    key={command.cmd}
                    className={`slash-item ${i === Math.min(hl, matchedCommands.length - 1) ? "hl" : ""}`}
                    onClick={() => { const arg = input.slice(command.cmd.length).trim(); void send(command.build(arg)); }}
                  >
                    <b>{command.cmd}</b>
                    <span className="text-soft">{command.hint}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="chat-input">
              <button className={`btn mic ${listening ? "listening" : ""}`} onClick={toggleMic} aria-label={listening ? "Ovozni to‘xtatish" : "Ovozli kiritish"} title="Ovozli kiritish (uz-UZ)">
                {listening ? <Square size={15} /> : <Mic size={17} />}
              </button>
              <textarea
                ref={textareaRef}
                className="textarea"
                placeholder="Xabar yozing yoki / buyruqlarni ko‘ring… (Enter — yuborish)"
                value={input}
                onChange={(event) => { setInput(event.target.value); setHl(0); }}
                onKeyDown={(event) => {
                  if (matchedCommands.length > 0 && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
                    event.preventDefault();
                    setHl((h) => event.key === "ArrowDown" ? Math.min(h + 1, matchedCommands.length - 1) : Math.max(0, h - 1));
                    return;
                  }
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (matchedCommands.length > 0 && input.trim().endsWith("/") === false && input.split(" ").length === 1 && matchedCommands.some((c) => c.cmd === input.trim())) {
                      const command = matchedCommands.find((c) => c.cmd === input.trim())!;
                      void send(command.build(""));
                      return;
                    }
                    void send(input);
                  }
                }}
              />
              <button className="btn primary chat-send" disabled={busy || input.trim().length === 0} onClick={() => void send(input)} aria-label="Yuborish">
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>

      <Drawer open={historyOpen} onClose={() => setHistoryOpen(false)} title="Suhbatlar">
        {historyList}
      </Drawer>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => void removeConversation()}
        title="Suhbatni o‘chirish"
        message={`«${deleteTarget?.title ?? ""}» suhbati va uning barcha xabarlari butunlay o‘chiriladi. Bu amalni qaytarib bo‘lmaydi. Davom etamizmi?`}
        confirmLabel="O‘chirish"
        danger
        busy={deleting}
      />
    </>
  );
}
