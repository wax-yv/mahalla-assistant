"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, ErrorNote } from "@/components/ui";
import { api } from "@/lib/api";

type Draft = {
  id: string;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
  result?: Record<string, unknown>;
  error?: string;
};
type Source = { type: string; label: string; url?: string; article?: string };
type Message = {
  id: string;
  role: string;
  content: string;
  agent?: string | null;
  sources?: Source[];
  draft_actions?: Draft[];
  created_at: string;
};
type Conversation = { id: string; title: string; updated_at: string; message_count: number };

const AGENT_LABELS: Record<string, string> = {
  orchestrator: "Orkestrator",
  document: "Hujjat agenti",
  reporting: "Hisobot agenti",
  legislation: "Qonunchilik agenti",
  credit_subsidy: "Kredit-subsidiya agenti",
  plan_control: "Reja va nazorat agenti",
};

const DRAFT_LABELS: Record<string, string> = {
  create_task: "Vazifa yaratish",
  create_case: "Murojaat ochish",
  create_worklog: "Ish yozuvini qo'rish",
  generate_report: "Hisobot yaratish",
  sync_legislation: "Qonunchilikni sinxronlash",
  save_preference: "Tanlovni saqlash",
  commit_import: "Importni bazaga yozish",
};

/* Slash-buyruqlar: / bilan yozilganda ko'rinadi, joy olmaydi */
const COMMANDS: Array<{ cmd: string; hint: string; build: (arg: string) => string }> = [
  { cmd: "/bugun", hint: "Bugungi vazifalar", build: () => "Bugun qaysi vazifalarga e'tibor berishim kerak?" },
  { cmd: "/kechikkan", hint: "Muddati o'tgan vazifalar", build: () => "Muddatidan oshgan vazifalar va shoshilinch murojaatlarni ko'rsat" },
  { cmd: "/vazifa", hint: "Vazifa loyihasi yaratish — /vazifa <matn>", build: (arg) => `vazifa yarat: ${arg || "Yangi topshiriq"}` },
  { cmd: "/hisobot", hint: "Hisobot — /hisobot [kunlik|haftalik|oylik]", build: (arg) => `${arg || "shu oy"} hisobot tayyorla` },
  { cmd: "/fuqaro", hint: "Fuqaro qidirish — /fuqaro <F.I.Sh. yoki telefon>", build: (arg) => `${arg} haqida ma'lumot ber` },
  { cmd: "/qonun", hint: "Qonunchilik — /qonun <savol>", build: (arg) => `qonun bo'yicha: ${arg}` },
  { cmd: "/kredit", hint: "Kredit-subsidiya — /kredit <bank>", build: (arg) => (arg ? `${arg} krediti shartlari qanday?` : "Kredit olishni xohlayman") },
  { cmd: "/import", hint: "Import holati va xatoliklar hisoboti", build: () => "Yuklagan faylimdagi xatoliklarni tahlil qilib ber" },
  { cmd: "/agentlar", hint: "Agentlar holati", build: () => "Agentlar holati qanday?" },
  { cmd: "/eksport", hint: "Eksport tartibi", build: () => "Eksport qilish tartibini tushuntir" },
];

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
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
  const [copied, setCopied] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [sttSupported, setSttSupported] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const loadConversations = useCallback(() => {
    api
      .get<{ items: Conversation[] }>("/agents/conversations")
      .then((data) => setConversations(data.items))
      .catch(() => {});
  }, []);

  const loadConversation = useCallback((id: string) => {
    setConversationId(id);
    api
      .get<{ messages: Message[] }>(`/agents/conversations/${id}`)
      .then((data) => setMessages(data.messages))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  useEffect(() => {
    void loadConversations();
    const w = window as unknown as Record<string, unknown>;
    setSttSupported(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, [loadConversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content: message, created_at: new Date().toISOString() },
    ]);
    try {
      const result = await api.post<{ conversation_id: string; message: Message; warnings: string[] }>(
        "/agents/chat",
        { message, conversation_id: conversationId }
      );
      setConversationId(result.conversation_id);
      setMessages((prev) => [...prev, result.message]);
      if (result.warnings.length) setError(result.warnings.join(" "));
      loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assistent javob bermadi.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(draft: Draft, approve: boolean) {
    try {
      await api.post(`/agents/drafts/${draft.id}/${approve ? "approve" : "reject"}`, {
        note: approve ? "Administrator tasdiqladi" : "Administrator rad etdi",
      });
      if (conversationId) loadConversation(conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Amal bajarilmadi.");
    }
  }

  async function removeConversation(id: string) {
    setConversations((prev) => prev.filter((item) => item.id !== id));
    if (conversationId === id) {
      setConversationId(null);
      setMessages([]);
    }
    try {
      await api.del(`/agents/conversations/${id}?purge=true`);
    } catch {
      loadConversations();
    }
  }

  function toggleMic() {
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Recognition) {
      setError("Brauzeringiz ovozli kiritishni qo'llab-quvvatlamaydi (Chrome tavsiya etiladi).");
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "uz-UZ";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript;
      }
      setInput((prev) => (prev ? `${prev} ${transcript.trim()}` : transcript.trim()));
    };
    recognition.onerror = () => setListening(false);
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
  const matchedCommands = slashQuery === null ? [] : COMMANDS.filter((c) => c.cmd.slice(1).includes(slashQuery.split(" ")[0]));

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">AI assistent · 5 agent + orkestrator</div>
          <h1>Suhbat</h1>
          <p className="lede">
            <code>/</code> ni bosing — tayyor buyruqlar chiqadi. Mikrofon bilan ovozli yozsa ham bo'ladi.
            Agentlar javobida manbalar ko'rsatiladi, yozuv amallari tasdiqingiz bilan bajariladi.
          </p>
        </div>
      </div>
      {error && <ErrorNote message={error} />}
      <div className="split s2r" style={{ alignItems: "start" }}>
        <div className="card card-pad" style={{ maxHeight: 520, overflowY: "auto" }}>
          <button
            className="btn primary"
            style={{ width: "100%", marginBottom: 12 }}
            onClick={() => {
              setConversationId(null);
              setMessages([]);
            }}
          >
            + Yangi suhbat
          </button>
          {conversations.map((conversation) => (
            <div key={conversation.id} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <button
                className="btn sm"
                style={{
                  flex: 1,
                  justifyContent: "flex-start",
                  minWidth: 0,
                  borderColor: conversationId === conversation.id ? "var(--brand)" : undefined,
                  background: conversationId === conversation.id ? "var(--brand-soft)" : undefined,
                }}
                onClick={() => loadConversation(conversation.id)}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {conversation.title}
                </span>
              </button>
              <button
                className="btn sm danger"
                title="Suhbatni o'chirish"
                aria-label="Suhbatni o'chirish"
                onClick={() => void removeConversation(conversation.id)}
              >
                🗑
              </button>
            </div>
          ))}
          {conversations.length === 0 && <p className="text-faint">Hozircha suhbat yo'q.</p>}
        </div>

        <div className="card card-pad">
          <div className="chat-wrap">
            <div className="chat-scroll" ref={scrollRef}>
              {messages.length === 0 && (
                <div className="empty">
                  <div className="icon">✦</div>
                  <h3>Assistentga savol bering</h3>
                  <p>
                    Xabar maydoniga <code>/</code> yozib tayyor buyruqlarni ko'ring — yoki ovozli tugma
                    bilan gapiring.
                  </p>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`msg ${message.role === "user" ? "user" : "bot"}`}>
                  {message.role !== "user" && (
                    <div className="tag" style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>{message.agent ? AGENT_LABELS[message.agent] ?? message.agent : "Assistent"}</span>
                      <button
                        className="chip"
                        style={{ padding: "1px 8px", fontSize: 11 }}
                        onClick={() => copyMessage(message)}
                      >
                        {copied === message.id ? "✓ nusxa olindi" : "nusxalash"}
                      </button>
                    </div>
                  )}
                  {message.content}
                  {(message.sources ?? []).length > 0 && (
                    <div className="sources">
                      {message.sources!.slice(0, 4).map((source, index) => (
                        <div key={index}>
                          ⌗ {source.label}
                          {source.url && (
                            <>
                              {" "}
                              <a className="link" href={source.url} target="_blank" rel="noreferrer">
                                ↗
                              </a>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {(message.draft_actions ?? []).map((draft) => (
                    <div className="draft-card" key={draft.id}>
                      <b>{DRAFT_LABELS[draft.action_type] ?? draft.action_type}</b>
                      <div className="mono" style={{ margin: "4px 0 8px" }}>
                        {JSON.stringify(draft.payload).slice(0, 160)}
                      </div>
                      {draft.status === "pending" ? (
                        <div style={{ display: "flex", gap: 8 }}>
                          <button className="btn sm primary" onClick={() => void decide(draft, true)}>
                            Tasdiqlash
                          </button>
                          <button className="btn sm danger" onClick={() => void decide(draft, false)}>
                            Rad etish
                          </button>
                        </div>
                      ) : (
                        <Badge tone={draft.status === "approved" ? "ok" : draft.status === "failed" ? "danger" : "muted"}>
                          {draft.status === "approved"
                            ? "Bajarildi"
                            : draft.status === "failed"
                              ? "Xatolik"
                              : "Rad etilgan"}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ))}
              {busy && (
                <div className="msg bot">
                  <div className="tag">Orkestrator</div>
                  Kerakli agentlar ishga tushirilmoqda…
                </div>
              )}
            </div>
            {matchedCommands.length > 0 && (
              <div className="slash-panel">
                {matchedCommands.map((command) => (
                  <button
                    key={command.cmd}
                    className="slash-item"
                    onClick={() => {
                      const arg = input.slice(command.cmd.length).trim();
                      void send(command.build(arg));
                    }}
                  >
                    <b className="mono">{command.cmd}</b>
                    <span className="text-soft">{command.hint}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="chat-input">
              <button
                className={`btn mic ${listening ? "listening" : ""}`}
                title={sttSupported ? "Ovozli kiritish (uz-UZ)" : "Brauzer qo'llab-quvvatlamaydi"}
                onClick={toggleMic}
                disabled={!sttSupported}
                aria-label="Ovozli kiritish"
              >
                {listening ? "⏹" : "🎙"}
              </button>
              <textarea
                ref={inputRef}
                className="textarea"
                placeholder="Xabar yozing yoki / buyruqlarni ko'ring… (Enter — yuborish)"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send(input);
                  }
                }}
              />
              <button className="btn primary" disabled={busy || input.trim().length === 0} onClick={() => void send(input)}>
                Yuborish
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
