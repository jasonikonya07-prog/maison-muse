import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw, Scale, Store } from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  createMarketplaceDispute,
  fetchMarketplaceOrders,
  fetchMarketplaceOrderSellers,
} from "../../services/api.js";
import "../../seller/Marketplace.css";

const FILTER_KEY = "mm-admin-marketplace-order-filters";
const DISPUTE_ACTIONS = [
  ["REFUND_REQUESTED", "Request buyer refund"],
  ["REFUND_RECORDED", "Record refund issued externally"],
  ["PENALTY_RECORDED", "Record vendor penalty"],
  ["RETURN_ACCEPTED", "Accept item return"],
  ["RETURN_REJECTED", "Reject item return"],
];
const STATUS_LABELS = {
  PENDING: "Pending packing",
  PROCESSING: "Packing",
  SHIPPED: "Dispatched",
  DELIVERED: "Delivered",
};

function readFilters() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(FILTER_KEY) ?? "{}");
    return {
      sellerId: typeof saved.sellerId === "string" ? saved.sellerId : "",
      status: ["", "PENDING", "PROCESSING", "SHIPPED", "DELIVERED"].includes(saved.status) ? saved.status : "",
    };
  } catch {
    return { sellerId: "", status: "" };
  }
}

function MarketplaceOrders({ canManage = false }) {
  const [filters, setFilters] = useState(readFilters);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [disputeTarget, setDisputeTarget] = useState(null);
  const [disputeForm, setDisputeForm] = useState({
    action: "REFUND_REQUESTED",
    reason: "",
    amount: "",
  });

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [orderRows, sellerRows] = await Promise.all([
        fetchMarketplaceOrders(filters),
        fetchMarketplaceOrderSellers(),
      ]);
      setOrders(orderRows);
      setVendors(sellerRows);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    try {
      window.localStorage.setItem(FILTER_KEY, JSON.stringify(filters));
    } catch (storageError) {
      console.error("Could not persist marketplace order filters.", storageError);
    }
  }, [filters]);

  const parentOrders = useMemo(() => {
    const grouped = new Map();
    for (const order of orders) {
      const parent = grouped.get(order.parent_order_id) ?? {
        parent_order_id: order.parent_order_id,
        order_number: order.order_number,
        customer: order.customer,
        created_at: order.created_at,
        seller_orders: [],
      };
      parent.seller_orders.push(order);
      grouped.set(order.parent_order_id, parent);
    }
    return [...grouped.values()];
  }, [orders]);

  const submitDispute = async (event) => {
    event.preventDefault();
    if (!disputeTarget) return;
    setSaving(true);
    setError("");
    try {
      await createMarketplaceDispute(disputeTarget.id, {
        action: disputeForm.action,
        reason: disputeForm.reason.trim(),
        amount: Number(disputeForm.amount || 0),
      });
      setDisputeTarget(null);
      setDisputeForm({ action: "REFUND_REQUESTED", reason: "", amount: "" });
      await refresh();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const openDispute = (order, action = "REFUND_REQUESTED") => {
    setDisputeTarget(order);
    setDisputeForm({ action, reason: "", amount: "" });
  };

  if (loading) return <section className="vendor-manager-panel"><p>Loading seller sub-orders…</p></section>;
  return (
    <div className="vendor-manager marketplace-orders">
      <header className="vendor-manager-heading"><div><span className="marketplace-eyebrow">MARKETPLACE OPERATIONS</span><h2>Multi-vendor orders</h2><p>Inspect customer parent orders and each seller’s separate fulfillment journey.</p></div><button type="button" className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Refresh</button></header>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      <section className="vendor-manager-panel">
        <div className="marketplace-order-filters">
          <label>Seller<select value={filters.sellerId} onChange={(event) => setFilters((current) => ({ ...current, sellerId: event.target.value }))}><option value="">All sellers</option>{vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.store_name}</option>)}</select></label>
          <label>Seller fulfillment<select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">All fulfillment statuses</option><option value="PENDING">Pending packing</option><option value="PROCESSING">Packing</option><option value="SHIPPED">Dispatched</option><option value="DELIVERED">Delivered</option></select></label>
          <span>{orders.length} seller sub-orders · {parentOrders.length} customer parent orders</span>
        </div>
        {parentOrders.length ? <div className="marketplace-parent-order-list">{parentOrders.map((parent) => <article className="marketplace-parent-order" key={parent.parent_order_id}>
          <header><div><span className="marketplace-eyebrow">CUSTOMER ORDER</span><h3>{parent.order_number}</h3><small>{parent.customer.name} · {parent.customer.phone} · {new Date(parent.created_at).toLocaleString()}</small></div><span>{parent.seller_orders.length} seller {parent.seller_orders.length === 1 ? "order" : "orders"}</span></header>
          <div className="marketplace-split-order-summary">{parent.seller_orders.map((order) => <span key={order.id}><Store size={13} /><strong>{order.seller_name}</strong>: {STATUS_LABELS[order.fulfillment_status]} · {formatKsh(order.seller_payout_amount)}</span>)}</div>
          <div className="marketplace-sub-order-list">{parent.seller_orders.map((order) => <section key={order.id} className="marketplace-sub-order">
            <header><div><strong>{order.seller_name}</strong><small>Sub-order #{order.id} · Customer payment {order.payment_status}</small></div><span className={`seller-status-badge ${order.fulfillment_status.toLowerCase()}`}>{STATUS_LABELS[order.fulfillment_status]}</span></header>
            <div className="marketplace-sub-order-lines">{order.items.map((item) => <span key={`${item.product_id}-${item.variant}`}>{item.quantity} × {item.product_name}{item.variant ? ` (${item.variant})` : ""} · {formatKsh(item.unit_price * item.quantity)}</span>)}</div>
            <div className="marketplace-sub-order-financials"><span>GMV <strong>{formatKsh(order.subtotal)}</strong></span><span>Commission <strong>{formatKsh(order.commission_amount)}</strong></span><span>Seller payout <strong>{formatKsh(order.seller_payout_amount)}</strong></span></div>
            {order.disputes.length > 0 && <div className="marketplace-dispute-history">{order.disputes.map((dispute) => <p key={dispute.id}><AlertTriangle size={13} /> <strong>{dispute.action.replaceAll("_", " ")}</strong> · {dispute.reason}{dispute.amount > 0 ? ` · ${formatKsh(dispute.amount)}` : ""} <small>{new Date(dispute.created_at).toLocaleString()}</small></p>)}</div>}
            {canManage && <div className="marketplace-dispute-actions"><button type="button" className="marketplace-button secondary" onClick={() => openDispute(order)}><Scale size={14} /> Resolve dispute</button><button type="button" className="marketplace-button secondary" onClick={() => openDispute(order, "PENALTY_RECORDED")}>Record fulfillment penalty</button><button type="button" className="marketplace-button secondary" onClick={() => openDispute(order, "RETURN_ACCEPTED")}>Manage return</button></div>}
          </section>)}</div>
        </article>)}</div> : <p className="marketplace-empty">{error ? "Orders are unavailable." : "Marketplace seller orders matching these filters will appear here."}</p>}
      </section>
      {canManage && disputeTarget && <div className="marketplace-modal-backdrop" onMouseDown={() => setDisputeTarget(null)}>
        <form className="marketplace-modal" onSubmit={submitDispute} onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">DISPUTE RESOLUTION</span><h2>Seller order #{disputeTarget.id}</h2></div></header>
          <p>{disputeTarget.order_number} · {disputeTarget.seller_name}</p>
          <label className="marketplace-review-reason">Resolution action<select value={disputeForm.action} onChange={(event) => setDisputeForm((current) => ({ ...current, action: event.target.value }))}>{DISPUTE_ACTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label className="marketplace-review-reason">Reason / case notes<textarea required minLength="3" maxLength="1000" rows="4" value={disputeForm.reason} onChange={(event) => setDisputeForm((current) => ({ ...current, reason: event.target.value }))} /></label>
          {["REFUND_RECORDED", "PENALTY_RECORDED"].includes(disputeForm.action) && <label className="marketplace-review-reason">Amount (KSh)<input type="number" min="0.01" step="0.01" required value={disputeForm.amount} onChange={(event) => setDisputeForm((current) => ({ ...current, amount: event.target.value }))} /></label>}
          {disputeForm.action === "REFUND_RECORDED" && <p className="commission-policy-note">This records a refund that was processed through the payment provider; it does not initiate a Pesapal refund.</p>}
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" onClick={() => setDisputeTarget(null)}>Cancel</button><button type="submit" className="marketplace-button primary" disabled={saving}>{saving ? "Recording…" : "Record resolution"}</button></footer>
        </form>
      </div>}
    </div>
  );
}

export default MarketplaceOrders;
