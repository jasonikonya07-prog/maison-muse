import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CreditCard,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  fetchAdminPayments,
  reconcileAdminPayment,
} from "../../services/api.js";

const STATUS_LABELS = {
  matched: "Matched",
  pending_callback: "Pending callback",
  processing: "Processing",
  payment_failed: "Payment failed",
  refunded: "Refunded",
  not_processed: "Not processed",
};

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function PaymentLogs({ canReconcile = false }) {
  const [search, setSearch] = useState("");
  const [data, setData] = useState({ gateway_configured: false, transactions: [], notice: "" });
  const [error, setError] = useState("");
  const [busyOrder, setBusyOrder] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await fetchAdminPayments(search));
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [search]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const reconcile = async (orderNumber) => {
    setBusyOrder(orderNumber);
    setError("");
    try {
      await reconcileAdminPayment(orderNumber);
      await load();
    } catch (reconcileError) {
      setError(reconcileError.message);
    } finally {
      setBusyOrder("");
    }
  };

  return (
    <div className="admin-ops-stack">
      {!data.gateway_configured && (
        <div className="admin-ops-banner warning"><ShieldAlert size={18} /><span><strong>Gateway not connected</strong>{data.notice || "No payment provider is configured. Internal orders cannot be verified against processor callbacks."}</span></div>
      )}
      {error && <div className="admin-ops-error" role="alert"><AlertCircle size={16} />{error}</div>}
      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">INTERNAL ORDER PAYMENT RECORDS</span><h2>Payment reconciliation <small>{data.transactions.length} records</small></h2></div>
          <label className="admin-table-search"><Search size={15} /><input placeholder="Find order ID" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        </header>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Gateway</th><th>Gateway reference</th><th>Internal order ID</th><th>Amount</th><th>Payment state</th><th>Created</th><th>Action</th></tr></thead>
            <tbody>{data.transactions.map((transaction) => (
              <tr key={transaction.order_id}>
                <td><span className="admin-ops-inline-icon"><CreditCard size={14} />{transaction.gateway}</span></td>
                <td>{transaction.gateway_reference ?? <span className="admin-ops-muted">Unavailable</span>}</td>
                <td><strong>{transaction.order_id}</strong></td>
                <td><strong>{formatKsh(transaction.amount)}</strong></td>
                <td><span className={`admin-ops-payment-state ${transaction.gateway_status}`}>{STATUS_LABELS[transaction.gateway_status] ?? transaction.payment_status}</span></td>
                <td>{formatTime(transaction.created_at)}</td>
                <td><button className="admin-button secondary small" onClick={() => reconcile(transaction.order_id)} disabled={!data.gateway_configured || !canReconcile || busyOrder === transaction.order_id} title={!data.gateway_configured ? "Configure a payment provider first" : !canReconcile ? "Your role cannot reconcile payments" : "Verify payment against the provider"}><RotateCcw size={13} />{busyOrder === transaction.order_id ? "Checking…" : "Reconcile"}</button></td>
              </tr>
            ))}
            {!data.transactions.length && <tr><td colSpan="7" className="admin-empty-copy">No internal orders match this search.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <p className="admin-ops-note"><RefreshCw size={13} /> Pesapal payment status is verified directly with the provider. Incoming IPN notifications trigger a server-side status check before an order is marked paid.</p>
    </div>
  );
}
