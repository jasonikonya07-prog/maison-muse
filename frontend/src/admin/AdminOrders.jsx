import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Eye,
  PackageCheck,
  Printer,
  RefreshCw,
  Search,
  ShieldAlert,
  Truck,
} from "lucide-react";
import { formatKsh } from "../data/currency.js";
import {
  createMarketplaceDispute,
  createOrderWebSocket,
  fetchAdminFulfillmentOrders,
  fetchMarketplaceOrderSellers,
  updateAdminFulfillmentStatus,
} from "../services/api.js";
import AdminOrderModal from "./components/AdminOrderModal.jsx";
import "./components/AdminOrders.css";

const STATUS_OPTIONS = [
  ["", "All fulfillment statuses"],
  ["PENDING_PACKING", "Pending packing"],
  ["PACKED", "Packed"],
  ["DISPATCHED_TO_COURIER", "Dispatched to courier"],
  ["OUT_FOR_DELIVERY", "Out for delivery"],
  ["DELIVERED", "Delivered"],
  ["CANCELLED", "Cancelled"],
];
const STATUS_LABELS = Object.fromEntries(STATUS_OPTIONS.slice(1).map(([value, label]) => [value, label]));

function AdminOrders({ canManage = false }) {
  const [orders, setOrders] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [inspector, setInspector] = useState(null);
  const [disputeTarget, setDisputeTarget] = useState(null);
  const [disputeReason, setDisputeReason] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [orderRows, vendorRows] = await Promise.all([
        fetchAdminFulfillmentOrders(),
        fetchMarketplaceOrderSellers(),
      ]);
      setOrders(orderRows);
      setVendors(vendorRows);
      setError("");
      setLoading(false);
      return orderRows;
    } catch (loadError) {
      setError(loadError.message);
      setLoading(false);
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const liveTrackingIds = useMemo(
    () =>
      [...new Set(
        orders
          .filter((order) => order.tracking_id && !["DELIVERED", "CANCELLED"].includes(order.fulfillment_status))
          .map((order) => order.tracking_id),
      )].slice(0, 40),
    [orders],
  );
  useEffect(() => {
    if (!liveTrackingIds.length) return undefined;
    const sockets = liveTrackingIds.map((trackingId) =>
      createOrderWebSocket(trackingId, {
        onMessage: (event) => {
          if (event.type === "status") refresh();
        },
      }),
    );
    return () => sockets.forEach((socket) => socket.close());
  }, [liveTrackingIds, refresh]);

  const filteredOrders = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return orders.filter((order) => {
      if (status && order.fulfillment_status !== status) return false;
      if (vendorId && String(order.seller_id) !== vendorId) return false;
      if (!term) return true;
      return [
        order.tracking_id,
        order.tracking_number,
        order.order_number,
        order.customer.name,
        order.customer.phone,
        order.customer.address,
        order.seller_name,
        order.fulfillment_status,
      ].some((value) => String(value ?? "").toLocaleLowerCase().includes(term));
    });
  }, [orders, search, status, vendorId]);

  const metrics = useMemo(() => {
    const today = new Date().toDateString();
    return [
      {
        label: "Total orders today",
        value: new Set(orders.filter((order) => new Date(order.created_at).toDateString() === today).map((order) => order.parent_order_id)).size,
        icon: PackageCheck,
        tone: "rose",
      },
      {
        label: "Pending packing",
        value: orders.filter((order) => order.fulfillment_status === "PENDING_PACKING").length,
        icon: PackageCheck,
        tone: "amber",
      },
      {
        label: "In transit",
        value: orders.filter((order) => ["DISPATCHED_TO_COURIER", "OUT_FOR_DELIVERY"].includes(order.fulfillment_status)).length,
        icon: Truck,
        tone: "blue",
      },
      {
        label: "Delivered successfully",
        value: orders.filter((order) => order.fulfillment_status === "DELIVERED").length,
        icon: PackageCheck,
        tone: "green",
      },
      {
        label: "Disputed orders",
        value: orders.filter((order) => order.disputes?.length > 0).length,
        icon: AlertTriangle,
        tone: "red",
      },
    ];
  }, [orders]);

  async function saveOverride(orderId, update) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateAdminFulfillmentStatus(orderId, update);
      const latest = await refresh();
      const updatedOrder = latest?.find((order) => order.id === orderId);
      if (updatedOrder) setInspector((current) => ({ ...current, order: updatedOrder }));
      setNotice(`Order #${orderId} fulfillment status was updated.`);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function escalateDispute(event) {
    event.preventDefault();
    if (!disputeTarget) return;
    setSaving(true);
    setError("");
    try {
      await createMarketplaceDispute(disputeTarget.id, {
        action: "REFUND_REQUESTED",
        reason: disputeReason.trim(),
        amount: 0,
      });
      setNotice(`A dispute was escalated for ${disputeTarget.order_number}.`);
      setDisputeTarget(null);
      setDisputeReason("");
      await refresh();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <section className="admin-orders"><p>Loading marketplace fulfillment data…</p></section>;
  }

  return (
    <section className="admin-orders">
      <header className="admin-orders-heading">
        <div>
          <span className="admin-overline">MARKETPLACE OPERATIONS</span>
          <h1>Order tracking &amp; fulfillment</h1>
          <p>Monitor seller shipments, payment escrow, and delivery exceptions across the marketplace.</p>
        </div>
        <button type="button" className="admin-button secondary" onClick={refresh}>
          <RefreshCw size={15} /> Refresh orders
        </button>
      </header>
      {error && <p className="admin-orders-message error" role="alert">{error}</p>}
      {notice && <p className="admin-orders-message success" role="status">{notice}</p>}
      <div className="admin-order-metrics">
        {metrics.map(({ label, value, icon: Icon, tone }) => (
          <article className={`admin-order-metric ${tone}`} key={label}>
            <span className="admin-order-metric-icon"><Icon size={17} /></span>
            <div><small>{label}</small><strong>{value.toLocaleString()}</strong></div>
          </article>
        ))}
      </div>
      <section className="admin-order-grid-panel">
        <div className="admin-order-filter-bar">
          <label className="admin-order-search">
            <Search size={16} />
            <input
              type="search"
              placeholder="Tracking ID, buyer, vendor, courier…"
              aria-label="Search order, tracking ID, buyer, vendor, or courier"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUS_OPTIONS.map(([value, label]) => <option value={value} key={value || "all"}>{label}</option>)}
            </select>
          </label>
          <label>
            Vendor
            <select value={vendorId} onChange={(event) => setVendorId(event.target.value)}>
              <option value="">All vendors</option>
              {vendors.map((vendor) => <option value={vendor.id} key={vendor.id}>{vendor.store_name}</option>)}
            </select>
          </label>
          <span className="admin-order-result-count">{filteredOrders.length} seller orders</span>
        </div>
        <div className="admin-order-table-wrap">
          <table className="admin-order-table">
            <thead>
              <tr>
                <th>Order &amp; placed</th>
                <th>Buyer &amp; delivery</th>
                <th>Vendor / boutique</th>
                <th>Items &amp; value</th>
                <th>Fulfillment</th>
                <th>Courier &amp; tracking</th>
                <th>Admin actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.map((order) => (
                <tr key={order.id} onClick={() => setInspector({ order, tab: "details" })}>
                  <td>
                    <strong>{order.order_number}</strong>
                    <small>Tracking: {order.tracking_id}</small>
                    <small>{new Date(order.created_at).toLocaleString()}</small>
                  </td>
                  <td>
                    <strong>{order.customer.name}</strong>
                    <a href={`tel:${order.customer.phone}`} onClick={(event) => event.stopPropagation()}>{order.customer.phone}</a>
                    <small className="admin-order-address">{order.customer.address}</small>
                  </td>
                  <td><strong>{order.seller_name}</strong><small>Seller order #{order.id}</small></td>
                  <td>
                    <strong>{formatKsh(order.subtotal)}</strong>
                    <small>{order.items.length} line item{order.items.length === 1 ? "" : "s"}</small>
                    <small className="admin-order-escrow">{order.payment_status.replaceAll("_", " ")} escrow</small>
                    <small>Order escrow {formatKsh(order.total)}</small>
                  </td>
                  <td><span className={`admin-order-status ${order.fulfillment_status.toLowerCase()}`}>{STATUS_LABELS[order.fulfillment_status] ?? order.fulfillment_status}</span></td>
                  <td>
                    <strong>{order.courier_name || "Not assigned"}</strong>
                    <small>{order.tracking_number || "Tracking pending"}</small>
                  </td>
                  <td onClick={(event) => event.stopPropagation()}>
                    <div className="admin-order-actions">
                      <button type="button" title="View master waybill" aria-label={`View waybill for ${order.order_number}`} onClick={() => setInspector({ order, tab: "waybill" })}><Printer size={15} /> View Waybill</button>
                      <button type="button" title="Inspect order and override status" aria-label={`Override status for ${order.order_number}`} disabled={!canManage} onClick={() => setInspector({ order, tab: "override" })}><Eye size={15} /> Override Status</button>
                      <button type="button" title="Escalate a dispute" aria-label={`Escalate dispute for ${order.order_number}`} disabled={!canManage} onClick={() => { setDisputeTarget(order); setDisputeReason(""); }}><ShieldAlert size={15} /> Escalate Dispute</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!filteredOrders.length && <tr><td className="admin-order-empty" colSpan="7">No seller orders match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {inspector && (
        <AdminOrderModal
          order={inspector.order}
          initialTab={inspector.tab}
          canManage={canManage}
          saving={saving}
          onClose={() => setInspector(null)}
          onOverride={saveOverride}
        />
      )}
      {disputeTarget && (
        <div className="admin-order-dispute-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setDisputeTarget(null);
        }}>
          <form className="admin-order-dispute-form" role="dialog" aria-modal="true" aria-labelledby="admin-dispute-title" onSubmit={escalateDispute}>
            <span className="admin-overline">MARKETPLACE RESOLUTION</span>
            <h2 id="admin-dispute-title">Escalate order dispute</h2>
            <p>{disputeTarget.order_number} · {disputeTarget.seller_name}</p>
            <label>Reason for escalation
              <textarea required minLength="3" maxLength="1000" value={disputeReason} onChange={(event) => setDisputeReason(event.target.value)} />
            </label>
            <div>
              <button type="button" className="admin-button secondary" onClick={() => setDisputeTarget(null)}>Cancel</button>
              <button type="submit" className="admin-button primary" disabled={saving}>{saving ? "Escalating…" : "Escalate dispute"}</button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

export default AdminOrders;
