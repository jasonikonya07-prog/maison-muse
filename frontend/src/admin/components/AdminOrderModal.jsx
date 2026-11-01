import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  PackageCheck,
  Printer,
  ShieldAlert,
  Truck,
  X,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import "./AdminOrders.css";

const OVERRIDE_STATUSES = [
  ["PENDING_PACKING", "Pending packing"],
  ["PACKED", "Packed"],
  ["DISPATCHED_TO_COURIER", "Dispatched to courier"],
  ["OUT_FOR_DELIVERY", "Out for delivery"],
  ["DELIVERED", "Delivered"],
  ["CANCELLED", "Cancelled"],
];
const STATUS_LABELS = {
  ORDER_PLACED: "Order placed",
  PENDING_PACKING: "Pending packing",
  PACKED: "Packed by vendor",
  DISPATCHED_TO_COURIER: "Dispatched to courier",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered successfully",
  CANCELLED: "Cancelled",
};

function AdminOrderModal({
  order,
  canManage = false,
  initialTab = "details",
  saving = false,
  onClose,
  onOverride,
}) {
  const [tab, setTab] = useState(initialTab);
  const overrideRef = useRef(null);
  const [qrCode, setQrCode] = useState("");
  const [qrError, setQrError] = useState("");
  const [form, setForm] = useState({
    status: order.fulfillment_status,
    courier_name: order.courier_name ?? "",
    tracking_number: order.tracking_number ?? "",
    note: "",
  });

  useEffect(() => {
    let active = true;
    setTab(initialTab);
    if (initialTab === "override") {
      window.setTimeout(() => overrideRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    }
    import("qrcode")
      .then(({ default: QRCode }) =>
        QRCode.toDataURL(order.tracking_number || order.tracking_id || order.order_number, {
          width: 180,
          margin: 1,
          errorCorrectionLevel: "M",
        }),
      )
      .then((dataUrl) => {
        if (active) setQrCode(dataUrl);
      })
      .catch((error) => {
        if (active) setQrError(`Could not create the waybill QR code: ${error.message}`);
      });
    return () => {
      active = false;
    };
  }, [initialTab, order.order_number, order.tracking_id, order.tracking_number]);

  async function submitOverride(event) {
    event.preventDefault();
    await onOverride(order.id, form);
  }

  const timeline = order.timeline?.length
    ? order.timeline
    : [{ status: "ORDER_PLACED", actor: "system", created_at: order.created_at }];

  return (
    <div className="admin-order-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <aside className="admin-order-drawer" role="dialog" aria-modal="true" aria-labelledby="admin-order-title">
        <header className="admin-order-drawer-header">
          <div>
            <span className="admin-overline">SELLER SUB-ORDER · #{order.id}</span>
            <h2 id="admin-order-title">{order.order_number}</h2>
            <p>{order.seller_name} · {new Date(order.created_at).toLocaleString()}</p>
          </div>
          <button type="button" className="admin-order-close" onClick={onClose} aria-label="Close order inspector">
            <X size={20} />
          </button>
        </header>
        <nav className="admin-order-tabs" aria-label="Order inspector sections">
          <button type="button" className={tab !== "waybill" ? "active" : ""} onClick={() => setTab("details")}>Order details</button>
          <button type="button" className={tab === "waybill" ? "active" : ""} onClick={() => setTab("waybill")}>Master waybill</button>
        </nav>

        {tab !== "waybill" ? (
          <div className="admin-order-drawer-content">
            <section className="admin-order-section">
              <div className="admin-order-section-title"><PackageCheck size={17} /><h3>Buyer &amp; delivery</h3></div>
              <div className="admin-order-buyer-grid">
                <span><small>Buyer</small><strong>{order.customer.name}</strong></span>
                <span><small>Phone</small><a href={`tel:${order.customer.phone}`}>{order.customer.phone}</a></span>
                <span className="wide"><small>Delivery address</small><strong>{order.customer.address}</strong></span>
              </div>
            </section>
            <section className="admin-order-section">
              <div className="admin-order-section-title"><Truck size={17} /><h3>Fulfillment timeline</h3></div>
              <ol className="admin-order-timeline">
                {timeline.map((event, index) => (
                  <li key={`${event.status}-${event.created_at}-${index}`}>
                    <span className="admin-order-timeline-icon">{index === timeline.length - 1 ? <CheckCircle2 size={15} /> : <Clock3 size={15} />}</span>
                    <div>
                      <strong>{STATUS_LABELS[event.status] ?? event.status.replaceAll("_", " ")}</strong>
                      {event.note && <p>{event.note}</p>}
                      <small>{new Date(event.created_at).toLocaleString()} · {event.actor}</small>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
            <section className="admin-order-section">
              <div className="admin-order-section-title"><PackageCheck size={17} /><h3>Itemized receipt</h3></div>
              <div className="admin-order-items">
                {order.items.map((item, index) => (
                  <div key={`${item.product_id ?? item.product_name}-${index}`}>
                    <span>{item.quantity} × {item.product_name}{item.variant ? ` · ${item.variant}` : ""}<small>{formatKsh(item.unit_price)} each</small></span>
                    <strong>{formatKsh(item.unit_price * item.quantity)}</strong>
                  </div>
                ))}
              </div>
              <div className="admin-order-split">
                <span>Gross item value<strong>{formatKsh(order.subtotal)}</strong></span>
                <span>Platform fee<strong>{formatKsh(order.commission_amount)}</strong></span>
                <span>Net vendor payout<strong>{formatKsh(order.seller_payout_amount)}</strong></span>
                <span className="escrow">Escrow status<strong>{order.payment_status.replaceAll("_", " ")}</strong></span>
              </div>
            </section>
            <section className="admin-order-section" ref={overrideRef}>
              <div className="admin-order-section-title"><ShieldAlert size={17} /><h3>Manual status override</h3></div>
              {canManage ? (
                <form className="admin-order-override-form" onSubmit={submitOverride}>
                  <label>Status
                    <select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}>
                      {OVERRIDE_STATUSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                    </select>
                  </label>
                  <div className="admin-order-override-grid">
                    <label>Courier
                      <input maxLength="100" value={form.courier_name} onChange={(event) => setForm((current) => ({ ...current, courier_name: event.target.value }))} placeholder="Fargo Courier" />
                    </label>
                    <label>Tracking number
                      <input maxLength="120" value={form.tracking_number} onChange={(event) => setForm((current) => ({ ...current, tracking_number: event.target.value }))} placeholder="Courier reference" />
                    </label>
                  </div>
                  <label>Admin note
                    <textarea maxLength="1000" value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))} placeholder="Reason for override (optional)" />
                  </label>
                  <button type="submit" className="admin-button primary" disabled={saving}>
                    {saving ? "Saving…" : "Apply status override"}
                  </button>
                </form>
              ) : (
                <p className="admin-order-readonly">Your admin role has read-only access to fulfillment overrides.</p>
              )}
            </section>
          </div>
        ) : (
          <div className="admin-order-drawer-content admin-order-waybill-content">
            <section className="admin-order-waybill">
              <header><span>MAISON MUSE</span><strong>MASTER SHIPPING LABEL</strong></header>
              <div className="admin-order-waybill-id"><strong>{order.order_number}</strong><span>Tracking ID: {order.tracking_id}</span></div>
              <div><small>DELIVER TO</small><strong>{order.customer.name}</strong><span>{order.customer.phone}</span><span>{order.customer.address}</span></div>
              <div><small>SELLER / BOUTIQUE</small><strong>{order.seller_name}</strong></div>
              <div><small>COURIER / REFERENCE</small><strong>{order.courier_name || "Not assigned"}</strong><span>{order.tracking_number || "Tracking reference pending"}</span></div>
              <div className="admin-order-waybill-lines">
                <small>PACKAGE CONTENTS</small>
                {order.items.map((item, index) => (
                  <span key={`${item.product_id ?? item.product_name}-${index}`}>{item.quantity} × {item.product_name}{item.variant ? ` · ${item.variant}` : ""}</span>
                ))}
              </div>
              {qrCode && <img src={qrCode} alt={`QR code for ${order.tracking_id}`} />}
              {qrError && <p className="admin-order-error" role="alert">{qrError}</p>}
              <small className="admin-order-waybill-scan">Scan to open the public tracking portal</small>
              <strong className="admin-order-waybill-value">{formatKsh(order.subtotal)}</strong>
            </section>
            <div className="admin-order-waybill-actions">
              <button type="button" className="admin-button secondary" onClick={() => setTab("details")}><ArrowLeft size={15} /> Back to details</button>
              <button type="button" className="admin-button primary" onClick={() => window.print()}><Printer size={15} /> Print shipping label</button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

export default AdminOrderModal;
