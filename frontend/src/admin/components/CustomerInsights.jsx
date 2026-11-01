import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Archive,
  Mail,
  MessageCircle,
  ShieldAlert,
  ShoppingBag,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import { fetchAdminCustomerInsights } from "../../services/api.js";

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function CustomerInsights() {
  const [insights, setInsights] = useState({
    abandoned_carts: [],
    cart_capture_enabled: false,
    cart_notice: "",
    risk_orders: [],
    risk_notice: "",
  });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setInsights(await fetchAdminCustomerInsights());
    } catch (loadError) {
      setError(loadError.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  return (
    <div className="admin-ops-stack">
      {error && <div className="admin-ops-error" role="alert"><AlertTriangle size={16} />{error}</div>}
      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">RECOVERY & RETENTION</span><h2>Abandoned checkout carts <small>{insights.abandoned_carts.length} carts</small></h2></div>
          <span className="admin-ops-status-muted">Capture {insights.cart_capture_enabled ? "enabled" : "not configured"}</span>
        </header>
        {!insights.cart_capture_enabled && (
          <div className="admin-ops-banner warning"><ShoppingBag size={18} /><span><strong>Cart recovery is not enabled</strong>{insights.cart_notice}</span></div>
        )}
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Cart</th><th>Customer contact</th><th>Items</th><th>Last checkout step</th><th>Last active</th><th>Actions</th></tr></thead>
            <tbody>{insights.abandoned_carts.map((cart) => (
              <tr key={cart.cart_id}>
                <td><strong>{cart.cart_id}</strong></td>
                <td>{cart.customer_phone || cart.customer_email || "Not provided"}</td>
                <td>{(cart.items ?? []).map((item) => `${item.name} × ${item.quantity}`).join(", ")}</td>
                <td>{cart.last_step}</td>
                <td>{formatTime(cart.last_active_at)}</td>
                <td><span className="admin-ops-toolbar">
                  <button className="admin-row-action" title="WhatsApp integration not configured" disabled><MessageCircle size={15} /></button>
                  <button className="admin-row-action" title="Email provider not configured" disabled><Mail size={15} /></button>
                  <button className="admin-row-action" title="Cart archive API not configured" disabled><Archive size={15} /></button>
                </span></td>
              </tr>
            ))}
            {!insights.abandoned_carts.length && <tr><td colSpan="6" className="admin-empty-copy">No abandoned-cart records are collected. Checkout contact details are only saved when an order is submitted.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">ORDER TRIAGE · NOT A FRAUD DECISION</span><h2>Risk signals <small>{insights.risk_orders.length} flagged</small></h2></div>
          <ShieldAlert className="admin-ops-rose-icon" size={19} />
        </header>
        <div className="admin-ops-banner warning"><AlertTriangle size={18} /><span><strong>Use as a review queue only</strong>{insights.risk_notice}</span></div>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Risk</th><th>Order</th><th>Customer</th><th>Amount</th><th>Failed attempts</th><th>Signals</th><th>Created</th></tr></thead>
            <tbody>{insights.risk_orders.map((order) => (
              <tr key={order.order_number}>
                <td><span className={`admin-ops-risk-score ${order.risk_score >= 80 ? "high" : "moderate"}`}>{order.risk_score}/100</span></td>
                <td><strong>{order.order_number}</strong></td>
                <td>{order.customer_name}<small className="admin-stock-threshold">{order.customer_phone}</small></td>
                <td>{formatKsh(order.amount)}</td>
                <td>{order.payment_attempts}</td>
                <td>{order.reasons.join(" · ")}</td>
                <td>{formatTime(order.created_at)}</td>
              </tr>
            ))}
            {!insights.risk_orders.length && <tr><td colSpan="7" className="admin-empty-copy">No current orders meet the configured review signals.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
