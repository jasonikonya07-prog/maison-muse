import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  CircleHelp,
  Clock3,
  PackageCheck,
  Search,
  ShieldCheck,
  Truck,
} from "lucide-react";
import { formatKsh } from "../data/currency.js";
import {
  createOrderWebSocket,
  fetchBuyerOrders,
  fetchBuyerOrderTracking,
} from "../services/api.js";
import "./BuyerOrderTracking.css";

const STEPS = [
  { status: "ORDER_PLACED", title: "Order placed", detail: "Payment and escrow confirmation" },
  { status: "PACKED", title: "Packed by vendor", detail: "Your boutique is preparing the order" },
  { status: "DISPATCHED_TO_COURIER", title: "Dispatched to courier", detail: "Handed over to the delivery partner" },
  { status: "OUT_FOR_DELIVERY", title: "Out for delivery", detail: "Courier is heading to your location" },
  { status: "DELIVERED", title: "Delivered successfully", detail: "Escrow release is eligible after delivery" },
];
const STATUS_INDEX = {
  ORDER_PLACED: 0,
  PENDING_PACKING: 0,
  PENDING: 0,
  PACKED: 1,
  PACKED_AND_READY: 1,
  PROCESSING: 1,
  DISPATCHED_TO_COURIER: 2,
  SHIPPED: 2,
  OUT_FOR_DELIVERY: 3,
  DELIVERED: 4,
  DELIVERED_SUCCESSFULLY: 4,
};

function BuyerOrderTracking() {
  const { trackingId: routeTrackingId = "" } = useParams();
  const navigate = useNavigate();
  const [buyer] = useState(() => {
    try {
      return JSON.parse(
        window.localStorage.getItem("mm-auth-user") ??
          window.localStorage.getItem("user_profile") ??
          "null",
      );
    } catch (error) {
      console.error("Unable to read the saved buyer profile.", error);
      return null;
    }
  });
  const [buyerOrders, setBuyerOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [query, setQuery] = useState(routeTrackingId);
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(Boolean(routeTrackingId));
  const [error, setError] = useState("");

  const refreshBuyerOrders = useCallback(async () => {
    setOrdersLoading(true);
    setOrdersError("");
    try {
      setBuyerOrders(await fetchBuyerOrders());
    } catch (loadError) {
      setOrdersError(loadError.message);
    } finally {
      setOrdersLoading(false);
    }
  }, []);

  useEffect(() => {
    if (buyer?.role !== "buyer") {
      setBuyerOrders([]);
      return undefined;
    }
    void refreshBuyerOrders();
  }, [buyer?.role, refreshBuyerOrders]);

  const lookup = useCallback(async (value) => {
    const normalized = value.trim();
    if (!normalized) {
      setError("Enter your order ID or courier tracking number.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setOrder(await fetchBuyerOrderTracking(normalized));
    } catch (lookupError) {
      setOrder(null);
      setError(lookupError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setQuery(routeTrackingId);
    if (routeTrackingId) lookup(routeTrackingId);
    else {
      setOrder(null);
      setError("");
    }
  }, [routeTrackingId, lookup]);

  useEffect(() => {
    if (!order?.tracking_id) return undefined;
    let active = true;
    let retryTimer;
    let socket;
    const connect = () => {
      if (!active) return;
      socket = createOrderWebSocket(order.tracking_id, {
        onMessage: (event) => {
          if (event.type === "status") lookup(order.tracking_id);
        },
        onClose: () => {
          if (active) retryTimer = window.setTimeout(connect, 2500);
        },
      });
    };
    connect();
    return () => {
      active = false;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [order?.tracking_id, lookup]);

  function submitSearch(event) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) {
      setError("Enter your order ID or courier tracking number.");
      return;
    }
    navigate(`/orders/${encodeURIComponent(normalized)}`);
  }

  function contactSupport() {
    window.dispatchEvent(new Event("maison-muse:support-open"));
  }

  return (
    <main className="buyer-tracking-page">
      <header className="buyer-tracking-header">
        <Link className="buyer-tracking-brand" to="/">maison <span>muse</span><i>.</i></Link>
        <Link className="buyer-tracking-home" to="/">Return to the store</Link>
      </header>
      <section className="buyer-tracking-hero">
        <span className="buyer-tracking-eyebrow"><ShieldCheck size={15} /> MAISON MUSE ORDER CARE</span>
        <h1>Your order, <em>in view.</em></h1>
        <p>Follow every handoff from your boutique to your doorstep, with live courier details.</p>
        <form className="buyer-tracking-search" role="search" onSubmit={submitSearch}>
          <Search size={18} />
          <input
            type="search"
            aria-label="Order ID or tracking number"
            placeholder="Enter order ID or tracking number"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" disabled={loading}>{loading ? "Checking…" : "Track order"} <ArrowRight size={15} /></button>
        </form>
        {error && <p className="buyer-tracking-error" role="alert">{error}</p>}
      </section>

      <section className="buyer-order-history" aria-labelledby="buyer-order-history-title">
        <div className="buyer-order-history-heading">
          <div>
            <span className="buyer-tracking-eyebrow">YOUR ACCOUNT</span>
            <h2 id="buyer-order-history-title">Your orders</h2>
          </div>
          {buyer?.role === "buyer" && (
            <button
              type="button"
              onClick={() => void refreshBuyerOrders()}
              disabled={ordersLoading}
            >
              Refresh orders
            </button>
          )}
        </div>
        {buyer?.role !== "buyer" ? (
          <p className="buyer-order-history-empty">
            Sign in as a buyer to see orders placed with your account. Guest orders can be
            found using the order ID or tracking number from the confirmation.
          </p>
        ) : ordersLoading ? (
          <p className="buyer-order-history-empty">Loading your orders…</p>
        ) : ordersError ? (
          <p className="buyer-tracking-error" role="alert">{ordersError}</p>
        ) : buyerOrders.length ? (
          <div className="buyer-order-history-list">
            {buyerOrders.map((buyerOrder) => (
              <article className="buyer-order-history-card" key={buyerOrder.order_number}>
                <div>
                  <strong>{buyerOrder.order_number}</strong>
                  <span>{new Date(buyerOrder.created_at).toLocaleString()}</span>
                </div>
                <div>
                  <strong>{formatKsh(buyerOrder.total)}</strong>
                  <span>
                    {buyerOrder.status.replaceAll("_", " ")} ·{" "}
                    {buyerOrder.payment_status.replaceAll("_", " ")}
                  </span>
                </div>
                <Link to={`/orders/${encodeURIComponent(buyerOrder.tracking_id)}`}>
                  Track order <ArrowRight size={14} />
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <p className="buyer-order-history-empty">
            No orders are linked to your account yet. Orders placed while signed in will
            appear here.
          </p>
        )}
      </section>

      {order && (
        <section className="buyer-tracking-results">
          <header className="buyer-tracking-order-summary">
            <div>
              <span className="buyer-tracking-eyebrow">ORDER TRACKING</span>
              <h2>{order.order_number}</h2>
              <p>Placed {new Date(order.created_at).toLocaleString()} · Tracking ID {order.tracking_id}</p>
            </div>
            <span className={`buyer-payment-badge ${["paid", "completed_demo"].includes(order.payment_status) ? "paid" : "pending"}`}>
              <ShieldCheck size={14} /> {["paid", "completed_demo"].includes(order.payment_status) ? "Escrow confirmed" : "Payment confirmation pending"}
            </span>
          </header>
          {order.packages.map((packageOrder) => {
            const activeIndex = STATUS_INDEX[packageOrder.status] ?? 0;
            const eventsByStatus = new Map(packageOrder.timeline.map((event) => [event.status, event]));
            return (
              <article className="buyer-tracking-package" key={packageOrder.id ?? order.order_number}>
                <header className="buyer-package-header">
                  <div>
                    <span className="buyer-tracking-eyebrow">FULFILLED BY</span>
                    <h3>{packageOrder.seller_name || "Maison Muse marketplace"}</h3>
                  </div>
                  <span className={`buyer-current-status ${packageOrder.status.toLowerCase()}`}>
                    {packageOrder.status.replaceAll("_", " ")}
                  </span>
                </header>
                {packageOrder.status === "CANCELLED" ? (
                  <p className="buyer-tracking-cancelled">This seller order was cancelled. Contact support if you need help with your refund.</p>
                ) : (
                  <ol className="buyer-order-steps">
                    {STEPS.map((step, index) => {
                      const completed = index <= activeIndex;
                      const event = eventsByStatus.get(step.status);
                      const placedEvent = index === 0 ? eventsByStatus.get("ORDER_PLACED") : event;
                      return (
                        <li key={step.status} className={completed ? "completed" : ""}>
                          <span className="buyer-step-marker">{completed ? <CheckCircle2 size={17} /> : <Clock3 size={16} />}</span>
                          <div>
                            <strong>{step.title}</strong>
                            <small>{event?.note || step.detail}</small>
                            {placedEvent?.created_at && <time>{new Date(placedEvent.created_at).toLocaleString()}</time>}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
                <div className="buyer-courier-card">
                  <Truck size={18} />
                  <div>
                    <small>Courier &amp; reference</small>
                    <strong>{packageOrder.courier_name || "Courier not assigned yet"}</strong>
                    <span>{packageOrder.tracking_number || "Tracking reference will appear after dispatch"}</span>
                  </div>
                </div>
                <div className="buyer-package-items">
                  {packageOrder.items.map((item, index) => (
                    <div key={`${item.product_id ?? item.product_name}-${index}`}>
                      <span>{item.quantity} × {item.product_name}{item.variant ? ` · ${item.variant}` : ""}</span>
                      <strong>{formatKsh(item.unit_price * item.quantity)}</strong>
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
          <aside className="buyer-receipt">
            <header><div><PackageCheck size={18} /><h3>Order receipt</h3></div><strong>{formatKsh(order.total)}</strong></header>
            <div><span>Items subtotal</span><strong>{formatKsh(order.subtotal)}</strong></div>
            <div><span>Shipping</span><strong>{formatKsh(order.shipping)}</strong></div>
            <div><span>Tax</span><strong>{formatKsh(order.tax)}</strong></div>
            <div className="buyer-receipt-total"><span>Total paid</span><strong>{formatKsh(order.total)}</strong></div>
            <p><strong>Deliver to</strong> {order.buyer.delivery_address}</p>
          </aside>
          <button type="button" className="buyer-support-button" onClick={contactSupport}>
            <CircleHelp size={17} /> Contact support
          </button>
        </section>
      )}
      {!order && !loading && !routeTrackingId && (
        <section className="buyer-tracking-empty">
          <PackageCheck size={25} />
          <h2>Ready when you are</h2>
          <p>Enter the order ID from your confirmation or the tracking code from your courier.</p>
        </section>
      )}
    </main>
  );
}

export default BuyerOrderTracking;
