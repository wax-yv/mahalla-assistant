"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, ErrorNote } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

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
  create_worklog: "Ish yozuvini qo‘shish",
  generate_report: "Hisobot yaratish",
  sync_legislation: "Qonunchilikni sinxronlash",
  save_preference: "Tanlovni saqlash",
};

const SUGGESTIONS = [
  "Bugun qaysi vazifalarga e'tibor berishim kerak?",
  "Zokirov Yusuf haqida ma'lumot ber",
  "Kredit olishni xohlayman",
  "Ishsizlik nafaqasi qonun bo'yicha qanday tayinlanadi?",
  "Shu oy uchun hisobot tayyorla",
  "Excel faylni qanday import qilaman?",
];

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

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
      const result = await api.post<{
        conversation_id: string;
        message: Message;
        warnings: string[];
      }>("/agents/chat", { message, conversation_id: conversationId });
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

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">AI assistent</div>
          <h1>Suhbat</h1>
          <p className="lede">
            Agentlar o‘zbek lotin tilida javob beradi. Raqamlar bazadan olinadi, qonunchilik
            manbalari Lex.uz dan, har bir yozuv amali esa tasdiqingiz bilan bajariladi.
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
            <button
              key={conversation.id}
              className="btn sm"
              style={{
                width: "100%",
                justifyContent: "flex-start",
                marginBottom: 6,
                borderColor: conversationId === conversation.id ? "var(--brand)" : undefined,
                background: conversationId === conversation.id ? "var(--brand-soft)" : undefined,
              }}
              onClick={() => loadConversation(conversation.id)}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {conversation.title}
              </span>
            </button>
          ))}
          {conversations.length === 0 && <p className="text-faint">Hozircha suhbat yo‘q.</p>}
        </div>

        <div className="card card-pad">
          <div className="chat-wrap">
            <div className="chat-scroll" ref={scrollRef}>
              {messages.length === 0 && (
                <div className="empty">
                  <div className="icon">✦</div>
                  <h3>Assistentga savol bering</h3>
                  <p>Masalan, vazifalar holati, fuqaro ma'lumoti, qonunchilik yoki kredit dasturlari bo‘yicha.</p>
                </div>
              )}
              {messages.map((message) => (
                <div key={message.id} className={`msg ${message.role === "user" ? "user" : "bot"}`}>
                  {message.role !== "user" && (
                    <div className="tag">
                      {message.agent ? AGENT_LABELS[message.agent] ?? message.agent : "Assistent"}
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
                  <div className="tag">Assistent</div>
                  Ma'lumotlar yig‘ilmoqda…
                </div>
              )}
            </div>
            <div className="chips">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} className="chip" onClick={() => void send(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
            <div className="chat-input">
              <textarea
                className="textarea"
                placeholder="Xabar yozing… (Enter — yuborish)"
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
