import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CircleAlert,
  Headphones,
  MessageCircle,
  RefreshCw,
  Send,
  UserRound,
} from "lucide-react";
import {
  createSupportWebSocket,
  fetchAdminSupportTicket,
  fetchAdminSupportTickets,
  replyAdminSupportTicket,
  updateAdminSupportTicketStatus,
} from "../services/api.js";
import "./AdminSupport.css";

const TABS = [
  { id: "all", label: "All Conversations" },
  { id: "waiting", label: "Waiting for Agent" },
  { id: "bot", label: "AI Bot Handled" },
  { id: "resolved", label: "Resolved" },
];
const CANNED_RESPONSES = [
  { label: "Refund approved", text: "Your refund has been approved. We’ll send you an update as soon as it has been processed." },
  { label: "Delivery update", text: "We’re checking the latest delivery update for your order and will share the tracking details shortly." },
  { label: "M-Pesa STK instructions", text: "Please confirm your M-Pesa line is active and can receive STK prompts. Keep checkout open and enter your PIN only on the official M-Pesa prompt." },
];

function messageKey(message) {
  return message.id ?? `${message.sender_type}-${message.timestamp}-${message.message}`;
}

function SupportMessage({ message }) {
  return (
    <article className={`admin-support-message ${message.sender_type.toLowerCase()}`}>
      <div className="admin-support-message-heading">
        <strong>{message.sender_name || (
          message.sender_type === "USER" ? "Customer" : "Maison Muse Support Bot"
        )}</strong>
        <time>{new Date(message.timestamp).toLocaleString()}</time>
      </div>
      {message.message && <p>{message.message}</p>}
      {message.attachments?.map((attachment) => (
        attachment.content_type?.startsWith("image/") ? (
          <a href={attachment.data_url} target="_blank" rel="noreferrer" key={attachment.name}>
            <img src={attachment.data_url} alt={attachment.name} />
            <small>{attachment.name}</small>
          </a>
        ) : (
          <a href={attachment.data_url} download={attachment.name} key={attachment.name}>
            {attachment.name}
          </a>
        )
      ))}
    </article>
  );
}

function AdminSupport({ canWrite = false }) {
  const [tickets, setTickets] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [ticketDetails, setTicketDetails] = useState(null);
  const [tab, setTab] = useState("all");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [socketConnected, setSocketConnected] = useState(false);
  const [agentsOnline, setAgentsOnline] = useState(0);
  const messagesRef = useRef(null);
  const socketRef = useRef(null);

  const loadTickets = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const results = await fetchAdminSupportTickets();
      setTickets(results);
      setError("");
      setSelectedId((current) =>
        current && results.some((ticket) => ticket.id === current)
          ? current
          : results[0]?.id ?? "",
      );
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTickets(true);
    const timer = window.setInterval(() => void loadTickets(), 8000);
    return () => window.clearInterval(timer);
  }, [loadTickets]);

  const selectedTicket =
    ticketDetails?.id === selectedId
      ? ticketDetails
      : tickets.find((ticket) => ticket.id === selectedId);
  const filteredTickets = useMemo(() => {
    if (tab === "waiting") return tickets.filter((ticket) => ticket.status === "WAITING_AGENT");
    if (tab === "bot") return tickets.filter((ticket) => ticket.status === "BOT");
    if (tab === "resolved") return tickets.filter((ticket) => ticket.status === "RESOLVED");
    return tickets;
  }, [tab, tickets]);
  const waitingCount = tickets.filter((ticket) => ticket.status === "WAITING_AGENT").length;

  useEffect(() => {
    if (!selectedId) return undefined;
    let active = true;
    fetchAdminSupportTicket(selectedId)
      .then((ticket) => {
        if (active) setTicketDetails(ticket);
      })
      .catch((detailError) => {
        if (active) setError(detailError.message);
      });
    const socket = createSupportWebSocket(selectedId, {
      onOpen: () => setSocketConnected(true),
      onClose: () => setSocketConnected(false),
      onMessage: (event) => {
        if (event.type === "presence") {
          setAgentsOnline(event.agents_online ?? 0);
          return;
        }
        if (event.type === "status") {
          setTickets((current) =>
            current.map((ticket) =>
              ticket.id === selectedId ? { ...ticket, status: event.status } : ticket,
            ),
          );
          setTicketDetails((current) =>
            current?.id === selectedId ? { ...current, status: event.status } : current,
          );
          return;
        }
        if (event.type !== "message" || !event.message) return;
        setTickets((current) =>
          current.map((ticket) => {
            if (ticket.id !== selectedId) return ticket;
            const lastMessage = ticket.last_message;
            return {
              ...ticket,
              last_message: event.message,
              message_count: (ticket.message_count ?? 0) + 1,
              ...(lastMessage && ticket.messages ? { messages: [...ticket.messages] } : {}),
            };
          }),
        );
        setTicketDetails((current) => {
          if (current?.id !== selectedId) return current;
          const existing = current.messages ?? [];
          if (existing.some((item) => messageKey(item) === messageKey(event.message))) {
            return current;
          }
          return { ...current, messages: [...existing, event.message] };
        });
      },
    });
    socketRef.current = socket;
    return () => {
      active = false;
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
      setSocketConnected(false);
    };
  }, [selectedId]);

  useEffect(() => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [selectedTicket?.messages]);

  async function sendReply(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!selectedTicket || !message || sending || !canWrite) return;
    setSending(true);
    setError("");
    try {
      const saved = await replyAdminSupportTicket(selectedTicket.id, message);
      setTickets((current) =>
        current.map((ticket) => {
          if (ticket.id !== selectedTicket.id) return ticket;
          if (ticket.last_message?.id === saved.id) return ticket;
          return {
            ...ticket,
            status: "WAITING_AGENT",
            last_message: saved,
            message_count: (ticket.message_count ?? 0) + 1,
          };
        }),
      );
      setTicketDetails((current) =>
        current?.id === selectedTicket.id &&
        !current.messages.some((item) => messageKey(item) === messageKey(saved))
          ? {
              ...current,
              status: "WAITING_AGENT",
              messages: [...current.messages, saved],
            }
          : current,
      );
      setDraft("");
    } catch (sendError) {
      setError(sendError.message);
    } finally {
      setSending(false);
    }
  }

  async function setTicketStatus(status) {
    if (!selectedTicket || !canWrite) return;
    setError("");
    try {
      await updateAdminSupportTicketStatus(selectedTicket.id, status);
      setTickets((current) =>
        current.map((ticket) =>
          ticket.id === selectedTicket.id ? { ...ticket, status } : ticket,
        ),
      );
    } catch (statusError) {
      setError(statusError.message);
    }
  }

  return (
    <section className="admin-support" aria-label="Customer support helpdesk">
      {waitingCount > 0 && (
        <div className="admin-support-priority" role="status">
          <CircleAlert size={18} />
          <span><strong>{waitingCount} conversation{waitingCount === 1 ? "" : "s"} waiting for an agent</strong><small>These customers asked to speak with live support.</small></span>
          <button type="button" onClick={() => setTab("waiting")}>View queue</button>
        </div>
      )}
      {error && <div className="admin-support-error" role="alert">{error}</div>}

      <div className="admin-support-layout">
        <aside className="admin-support-inbox">
          <header>
            <div><span className="admin-overline">SUPPORT QUEUE</span><h2>Conversations</h2></div>
            <button type="button" aria-label="Refresh conversations" onClick={() => void loadTickets(true)}><RefreshCw size={16} /></button>
          </header>
          <nav className="admin-support-tabs" aria-label="Filter support conversations">
            {TABS.map((item) => (
              <button
                type="button"
                key={item.id}
                className={tab === item.id ? "is-active" : ""}
                aria-pressed={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {item.id === "waiting" && waitingCount > 0 && <i>{waitingCount}</i>}
              </button>
            ))}
          </nav>
          <div className="admin-support-ticket-list">
            {loading ? (
              <p className="admin-support-empty">Loading conversations…</p>
            ) : filteredTickets.length ? (
              filteredTickets.map((ticket) => {
                const lastMessage = ticket.messages?.at(-1);
                return (
                  <button
                    type="button"
                    key={ticket.id}
                    className={`admin-support-ticket ${selectedId === ticket.id ? "is-selected" : ""}`}
                    onClick={() => setSelectedId(ticket.id)}
                  >
                    <span className="admin-support-avatar"><UserRound size={17} /></span>
                    <span className="admin-support-ticket-copy">
                      <strong>{ticket.customer?.name || "Guest customer"}</strong>
                      <small>{lastMessage?.message || "Attachment shared"}</small>
                    </span>
                    <span className={`admin-support-status ${ticket.status.toLowerCase()}`}>
                      {ticket.status === "WAITING_AGENT" ? "Waiting" : ticket.status === "RESOLVED" ? "Resolved" : "Bot"}
                    </span>
                  </button>
                );
              })
            ) : (
              <p className="admin-support-empty">No conversations in this queue yet.</p>
            )}
          </div>
        </aside>

        <div className="admin-support-console">
          {selectedTicket ? (
            <>
              <header className="admin-support-conversation-header">
                <div>
                  <span className="admin-overline">CUSTOMER CONVERSATION</span>
                  <h2>{selectedTicket.customer?.name || "Guest customer"}</h2>
                  <p>{selectedTicket.customer?.email || "No email provided"}{selectedTicket.customer?.phone ? ` · ${selectedTicket.customer.phone}` : ""}</p>
                </div>
                <span className={`admin-support-live ${socketConnected ? "connected" : ""}`}>
                  <i />{agentsOnline > 0 ? `${agentsOnline} agent${agentsOnline === 1 ? "" : "s"} online` : socketConnected ? "Connected" : "Connecting"}
                </span>
              </header>

              <div className="admin-support-customer-context">
                <section>
                  <strong><UserRound size={14} /> Customer profile</strong>
                  <span>{selectedTicket.customer?.authenticated ? "Signed-in customer" : "Guest session"}</span>
                  <small>{selectedTicket.customer?.phone || "Phone not provided"}</small>
                </section>
                <section>
                  <strong>Recent orders</strong>
                  {selectedTicket.orders?.length ? selectedTicket.orders.map((order) => (
                    <small key={order.order_number}>{order.order_number} · {order.status}</small>
                  )) : <small>No orders matched this customer.</small>}
                </section>
                <section>
                  <strong>Active cart</strong>
                  {selectedTicket.cart_items?.length ? selectedTicket.cart_items.map((item, index) => (
                    <small key={`${item.name}-${index}`}>{item.quantity} × {item.name}</small>
                  )) : <small>No cart items were shared.</small>}
                </section>
              </div>

              <div className="admin-support-conversation-toolbar">
                <span className={`admin-support-status ${selectedTicket.status.toLowerCase()}`}>
                  {selectedTicket.status.replaceAll("_", " ")}
                </span>
                {canWrite && (
                  <div>
                    {selectedTicket.status === "BOT" ? (
                      <button type="button" onClick={() => void setTicketStatus("WAITING_AGENT")}>Take Over from AI Bot</button>
                    ) : selectedTicket.status === "WAITING_AGENT" ? (
                      <>
                        <button type="button" onClick={() => void setTicketStatus("BOT")}>Re-assign to AI Bot</button>
                        <button type="button" onClick={() => void setTicketStatus("RESOLVED")}>Resolve conversation</button>
                      </>
                    ) : (
                      <button type="button" onClick={() => void setTicketStatus("WAITING_AGENT")}>Reopen conversation</button>
                    )}
                  </div>
                )}
              </div>

              <div className="admin-support-thread" ref={messagesRef} aria-live="polite">
                {(selectedTicket.messages ?? []).map((message) => (
                  <SupportMessage message={message} key={messageKey(message)} />
                ))}
              </div>

              {canWrite ? (
                <>
                  <div className="admin-support-canned">
                    {CANNED_RESPONSES.map((response) => (
                      <button type="button" key={response.label} onClick={() => setDraft(response.text)}>
                        {response.label}
                      </button>
                    ))}
                  </div>
                  <form className="admin-support-reply" onSubmit={sendReply}>
                    <textarea
                      rows="2"
                      maxLength="2000"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder="Reply as Admin Support…"
                      aria-label="Admin support reply"
                      required
                    />
                    <button className="admin-button primary" type="submit" disabled={sending || !draft.trim()}>
                      {sending ? <Check size={15} /> : <Send size={15} />}
                      {sending ? "Sent" : "Send reply"}
                    </button>
                  </form>
                </>
              ) : (
                <p className="admin-support-read-only">Your role can view support conversations but cannot reply.</p>
              )}
            </>
          ) : (
            <div className="admin-support-no-selection">
              <span><MessageCircle size={25} /></span>
              <h2>Customer Support &amp; Bot Conversations</h2>
              <p>Select a conversation to view its messages and customer details.</p>
              {!tickets.length && !loading && <small>New conversations will appear here as customers contact support.</small>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default AdminSupport;
