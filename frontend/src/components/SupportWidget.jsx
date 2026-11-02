import { useEffect, useRef, useState } from "react";
import { Headphones, MessageCircle, Paperclip, Send, X, Minimize2 } from "lucide-react";
import { useFeatures } from "../context/FeatureContext.jsx";
import {
  createSupportWebSocket,
  fetchSupportTicket,
  sendSupportMessage,
} from "../services/api.js";
import "./SupportWidget.css";

const SESSION_KEY = "mm-support-session";
const QUICK_ACTIONS = [
  { intent: "order_status", label: "Where is my order?" },
  { intent: "order_cancel", label: "Cancel or change an order" },
  { intent: "refund_return", label: "Returns and refunds" },
  { intent: "seller_account_blocked", label: "My seller account is blocked" },
  { intent: "seller_signup", label: "How do I sell on Maison Muse?" },
  { intent: "mpesa_help", label: "M-Pesa payment issue" },
  { intent: "human", label: "Talk to a Live Support Agent" },
];
const FALLBACK_REPLY =
  "I couldn't match that to a topic yet. Ask about Seller Plans, M-Pesa, or connect with a live admin using one of the options below.";
const FALLBACK_ACTIONS = [
  { intent: "seller_plans", label: "Ask about Seller Plans" },
  { intent: "mpesa_help", label: "Ask about M-Pesa" },
  { intent: "human", label: "Connect with Live Admin" },
];
const ALLOWED_FILE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);
const MAX_FILE_SIZE = 2 * 1024 * 1024;

function readSupportSession() {
  try {
    const saved = window.localStorage.getItem(SESSION_KEY);
    return saved ? JSON.parse(saved) : { ticketId: "", token: "", unread: 0 };
  } catch (error) {
    console.error("Unable to read the saved support conversation.", error);
    return { ticketId: "", token: "", unread: 0 };
  }
}

function messageKey(message) {
  return message.id ?? `${message.sender_type}-${message.timestamp}-${message.message}`;
}

function SupportWidget() {
  const { liveSupportBot, whatsappDirectBypass } = useFeatures();
  const savedSession = useRef(readSupportSession()).current;
  const [ticketId, setTicketId] = useState(savedSession.ticketId ?? "");
  const [token, setToken] = useState(savedSession.token ?? "");
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("BOT");
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(savedSession.unread ?? 0);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [agentsOnline, setAgentsOnline] = useState(0);
  const messagesRef = useRef(null);
  const socketRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const openSupportWidget = () => setOpen(true);
    window.addEventListener("maison-muse:support-open", openSupportWidget);
    return () =>
      window.removeEventListener("maison-muse:support-open", openSupportWidget);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SESSION_KEY,
        JSON.stringify({ ticketId, token, unread }),
      );
    } catch (storageError) {
      console.error("Unable to save the support conversation.", storageError);
    }
  }, [ticketId, token, unread]);

  useEffect(() => {
    if (!ticketId || !token) return undefined;
    let active = true;
    fetchSupportTicket(ticketId, token)
      .then((ticket) => {
        if (!active) return;
        setStatus(ticket.status);
        setMessages(ticket.messages);
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError.message);
      });
    return () => {
      active = false;
    };
  }, [ticketId, token]);

  useEffect(() => {
    if (!ticketId) return undefined;
    let active = true;
    let retryTimer;

    const connect = () => {
      if (!active) return;
      const socket = createSupportWebSocket(ticketId, {
        onClose: () => {
          if (active) retryTimer = window.setTimeout(connect, 2500);
        },
        onMessage: (event) => {
          if (event.type === "presence") {
            setAgentsOnline(event.agents_online ?? 0);
            return;
          }
          if (event.type === "status") {
            setStatus(event.status);
            return;
          }
          if (event.type !== "message" || !event.message) return;
          setMessages((current) => {
            if (current.some((item) => messageKey(item) === messageKey(event.message))) {
              return current;
            }
            if (!open && event.message.sender_type !== "USER") {
              setUnread((count) => count + 1);
            }
            return [...current, event.message];
          });
        },
      });
      socketRef.current = socket;
    };
    connect();
    return () => {
      active = false;
      window.clearTimeout(retryTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [open, ticketId]);

  useEffect(() => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, open]);

  const appendMessages = (incoming) => {
    setMessages((current) => {
      const merged = new Map(current.map((message) => [messageKey(message), message]));
      incoming.forEach((message) => {
        const key = messageKey(message);
        merged.set(key, { ...merged.get(key), ...message });
      });
      return [...merged.values()];
    });
  };

  async function submitMessage(event, intent = "message", quickAction = "") {
    event?.preventDefault();
    if (busy) return;
    const message = quickAction || draft.trim();
    if (!message && !attachment) return;
    setBusy(true);
    setError("");
    try {
      const response = await sendSupportMessage(
        {
          ticket_id: ticketId || undefined,
          message,
          intent,
          attachments: attachment ? [attachment] : [],
        },
        token,
      );
      setTicketId(response.ticket_id);
      setToken(response.access_token);
      setStatus(response.status);
      appendMessages([
        ...(response.messages ?? []).filter(
          (message) => message.id !== response.bot_reply?.id,
        ),
        ...(response.bot_reply ? [response.bot_reply] : []),
      ]);
      setDraft("");
      setAttachment(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (sendError) {
      setError(sendError.message);
    } finally {
      setBusy(false);
    }
  }

  function chooseAttachment(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!ALLOWED_FILE_TYPES.has(file.type) || file.size > MAX_FILE_SIZE) {
      setError("Attach a PNG, JPEG, WebP image, or PDF up to 2 MB.");
      event.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setAttachment({
          name: file.name,
          content_type: file.type,
          data_url: reader.result,
        });
        setError("");
      }
    };
    reader.onerror = () => setError("The attachment could not be read. Please try again.");
    reader.readAsDataURL(file);
  }

  if (!liveSupportBot) return null;

  return (
    <div className="support-widget">
      {open && (
        <section className="support-window" role="dialog" aria-label="Maison Muse customer support">
          <header className="support-window-header">
            <span className="support-header-icon"><Headphones size={19} /></span>
            <span className="support-header-copy">
              <strong>Maison Muse Support Bot</strong>
              <small><i /> {agentsOnline ? "Live support agent online" : "Support bot online"}</small>
            </span>
            <button type="button" aria-label="Minimize support chat" onClick={() => setOpen(false)}>
              <Minimize2 size={17} />
            </button>
            <button type="button" aria-label="Close support chat" onClick={() => setOpen(false)}>
              <X size={18} />
            </button>
          </header>

          <div className="support-chat-status" role="status">
            <span className={`support-status-chip status-${status.toLowerCase()}`}>
              {status === "WAITING_AGENT"
                ? "Waiting for a support agent"
                : status === "RESOLVED"
                  ? "Conversation resolved"
                  : "Maison Muse Support"}
            </span>
          </div>

          <div className="support-message-feed" ref={messagesRef} aria-live="polite">
            {messages.map((message) => (
              <article
                className={`support-message ${message.sender_type.toLowerCase()}`}
                key={messageKey(message)}
              >
                {message.sender_type !== "USER" && (
                  <strong>{message.sender_name || "Maison Muse Support"}</strong>
                )}
                {message.message && <p>{message.message}</p>}
                {message.sender_type === "BOT" &&
                  (message.suggested_actions ??
                    (message.message === FALLBACK_REPLY ? FALLBACK_ACTIONS : [])
                  ).length > 0 && (
                    <div className="support-quick-actions" aria-label="Suggested support topics">
                      {(message.suggested_actions ??
                        (message.message === FALLBACK_REPLY ? FALLBACK_ACTIONS : [])
                      ).map((action) => (
                        <button
                          className={action.intent === "human" ? "human-action" : ""}
                          key={action.intent}
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            submitMessage(undefined, action.intent, action.label)
                          }
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  )}
                {message.sender_type === "BOT" &&
                    /^Order .+ is currently .+\./.test(message.message) && (
                    <span className="support-order-status-chip">
                        {message.message.match(/^Order .+ is currently (.+?)\./)?.[1]}
                    </span>
                  )}
                {message.attachments?.map((file) => (
                  file.content_type.startsWith("image/") ? (
                    <a href={file.data_url} target="_blank" rel="noreferrer" key={file.name}>
                      <img src={file.data_url} alt={file.name} />
                      <small>{file.name}</small>
                    </a>
                  ) : (
                    <a href={file.data_url} download={file.name} key={file.name}>
                      <Paperclip size={14} /> {file.name}
                    </a>
                  )
                ))}
                <time>{new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
              </article>
            ))}
            {!messages.length && (
              <p className="support-welcome">
                Hello! I’m the Maison Muse Support Bot. How can I help today?
              </p>
            )}
            {!messages.some((message) => message.sender_type === "USER") && (
              <div className="support-quick-actions" aria-label="Quick support actions">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    className={action.intent === "human" ? "human-action" : ""}
                    key={action.intent}
                    type="button"
                    disabled={busy}
                    onClick={() => submitMessage(undefined, action.intent, action.label)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {error && <p className="support-error" role="alert">{error}</p>}
          {attachment && (
            <div className="support-attachment-preview">
              <Paperclip size={14} /><span>{attachment.name}</span>
              <button type="button" onClick={() => setAttachment(null)} aria-label="Remove attachment"><X size={14} /></button>
            </div>
          )}
          <form className="support-compose" onSubmit={submitMessage}>
            <input
              ref={fileInputRef}
              className="support-file-input"
              type="file"
              accept="image/png,image/jpeg,image/webp,application/pdf"
              onChange={chooseAttachment}
              aria-label="Attach a file"
            />
            <button
              type="button"
              className="support-attach-button"
              aria-label="Attach a file"
              onClick={() => fileInputRef.current?.click()}
            >
              <Paperclip size={17} />
            </button>
            <textarea
              rows="1"
              maxLength="2000"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Write a message…"
              aria-label="Write a message"
            />
            <button
              className="support-send-button"
              type="submit"
              disabled={busy || (!draft.trim() && !attachment)}
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </form>
          <footer className="support-window-footer">
            {status === "WAITING_AGENT"
              ? "A support agent will reply here. Never send passwords, codes, PINs, or payment details or documents."
              : whatsappDirectBypass
                ? "We typically reply within a few minutes. Never send passwords, codes, PINs, payment details, or private documents."
                : "Message us anytime. Never send passwords, codes, PINs, payment details, or private documents."}
          </footer>
        </section>
      )}
      <button
        className={`support-launcher ${open ? "is-open" : ""}`}
        type="button"
        aria-label={open ? "Close customer support chat" : "Open customer support chat"}
        aria-expanded={open}
        onClick={() => {
          setOpen((current) => !current);
          setUnread(0);
        }}
      >
        {open ? <X size={22} /> : <MessageCircle size={23} />}
        {!open && unread > 0 && <span className="support-unread-badge">{unread > 9 ? "9+" : unread}</span>}
      </button>
    </div>
  );
}

export default SupportWidget;
