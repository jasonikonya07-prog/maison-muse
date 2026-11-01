import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  PackageCheck,
  Printer,
  RefreshCw,
  Truck,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  createOrderWebSocket,
  fetchSellerOrders,
  updateSellerFulfillment,
} from "../../services/api.js";
import "./OrderFulfillment.css";

const STATUS_LABELS = {
  PENDING: "Pending packing",
  PENDING_PACKING: "Pending packing",
  PROCESSING: "Packed and ready",
  PACKED: "Packed and ready",
  PACKED_AND_READY: "Packed and ready",
  SHIPPED: "Dispatched to courier",
  DISPATCHED_TO_COURIER: "Dispatched to courier",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  DELIVERED_TO_CUSTOMER: "Delivered",
  CANCELLED: "Cancelled",
};
const NEXT_STATUS = {
  PENDING: ["PACKED_AND_READY", "Pack order"],
  PENDING_PACKING: ["PACKED_AND_READY", "Pack order"],
  PROCESSING: ["DISPATCHED_TO_COURIER", "Dispatch order"],
  PACKED: ["DISPATCHED_TO_COURIER", "Dispatch order"],
  PACKED_AND_READY: ["DISPATCHED_TO_COURIER", "Dispatch order"],
  SHIPPED: ["DELIVERED_TO_CUSTOMER", "Mark delivered"],
  DISPATCHED_TO_COURIER: ["DELIVERED_TO_CUSTOMER", "Mark delivered"],
  OUT_FOR_DELIVERY: ["DELIVERED_TO_CUSTOMER", "Mark delivered"],
};

function OrderFulfillment({ readOnly = false }) {
  const [orders, setOrders] = useState([]);
  const [dispatch, setDispatch] = useState({});
  const [nextStatuses, setNextStatuses] = useState({});
  const [slip, setSlip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const currentOrders = await fetchSellerOrders();
      setOrders(currentOrders);
      setError("");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const liveTrackingIds = useMemo(
    () =>
      orders
        .filter(
          (order) =>
            order.tracking_id &&
            !["DELIVERED", "CANCELLED"].includes(order.tracking_status ?? order.fulfillment_status),
        )
        .slice(0, 40)
        .map((order) => order.tracking_id),
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

  async function advance(order) {
    if (readOnly) return;
    const next = NEXT_STATUS[order.tracking_status ?? order.fulfillment_status];
    if (!next) return;
    const targetStatus = nextStatuses[order.id] ?? next[0];
    const fields = dispatch[order.id] ?? {
      courier_name: order.courier_name ?? "",
      tracking_number: order.tracking_number ?? "",
    };
    setSavingId(order.id);
    setError("");
    setNotice("");
    try {
      await updateSellerFulfillment(order.id, targetStatus, fields);
      setNotice(`${order.order_number} updated to ${STATUS_LABELS[targetStatus]}.`);
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setSavingId(null);
    }
  }

  async function openWaybill(order) {
    setError("");
    try {
      const { default: QRCode } = await import("qrcode");
      const qrCode = await QRCode.toDataURL(
        order.tracking_id || order.order_number,
        { width: 180, margin: 1, errorCorrectionLevel: "M" },
      );
      setSlip({ ...order, qrCode });
    } catch (qrError) {
      setError(`Could not create the package QR code: ${qrError.message}`);
    }
  }

  if (loading) {
    return (
      <section className="seller-panel fulfillment-hub">
        <p>Loading fulfillment queue…</p>
      </section>
    );
  }

  return (
    <section className="seller-panel fulfillment-hub">
      <header className="fulfillment-heading">
        <div>
          <span className="marketplace-eyebrow">LIVE ORDER QUEUE</span>
          <h2>Order fulfillment <small>{orders.length} orders</small></h2>
        </div>
        <button type="button" className="marketplace-button secondary" onClick={refresh}>
          <RefreshCw size={15} /> Refresh queue
        </button>
      </header>
      {error && <p className="fulfillment-message error" role="alert">{error}</p>}
      {notice && <p className="fulfillment-message success" role="status">{notice}</p>}
      {orders.length ? (
        <div className="fulfillment-order-list">
          {orders.map((order) => {
            const fulfillmentStatus = order.tracking_status ?? order.fulfillment_status;
            const next = NEXT_STATUS[fulfillmentStatus];
            const fields = dispatch[order.id] ?? {
              courier_name: order.courier_name ?? "",
              tracking_number: order.tracking_number ?? "",
            };
            const terminal = ["DELIVERED", "CANCELLED"].includes(fulfillmentStatus);
            return (
              <article className="fulfillment-order-card" key={order.id}>
                <header className="fulfillment-order-top">
                  <div>
                    <span className="marketplace-eyebrow">ORDER {order.order_number}</span>
                    <h3>{order.customer.name}</h3>
                    <small>{new Date(order.ordered_at).toLocaleString()}</small>
                  </div>
                  <span className={`seller-status-badge ${fulfillmentStatus.toLowerCase()}`}>
                    {STATUS_LABELS[fulfillmentStatus] ?? fulfillmentStatus}
                  </span>
                </header>
                <p className="fulfillment-items">
                  {order.items.map((item) =>
                    `${item.quantity} × ${item.product_name}${item.variant ? ` (${item.variant})` : ""}`,
                  ).join(" · ")}
                </p>
                <p className="fulfillment-address">
                  Deliver to {order.customer.phone} · {order.customer.address}
                </p>
                <div className="fulfillment-dispatch-grid">
                  <label>
                    Courier service
                    <select
                      value={fields.courier_name}
                      disabled={readOnly || terminal || savingId === order.id}
                      onChange={(event) =>
                        setDispatch((current) => ({
                          ...current,
                          [order.id]: { ...fields, courier_name: event.target.value },
                        }))
                      }
                    >
                      <option value="">Select courier</option>
                      <option>Fargo Courier</option>
                      <option>G4S</option>
                      <option>Bodaboda Express</option>
                      <option>Other / Local courier</option>
                    </select>
                  </label>
                  <label>
                    Tracking reference
                    <input
                      value={fields.tracking_number}
                      placeholder="Enter courier tracking code"
                      disabled={readOnly || terminal || savingId === order.id}
                      onChange={(event) =>
                        setDispatch((current) => ({
                          ...current,
                          [order.id]: { ...fields, tracking_number: event.target.value },
                        }))
                      }
                    />
                  </label>
                </div>
                <footer className="fulfillment-order-footer">
                  <span>
                    Vendor payout <strong>{formatKsh(order.seller_payout_amount)}</strong>
                    <small>
                      {order.payment_status === "paid" || order.payment_status === "completed_demo"
                        ? "Escrow paid"
                        : "Escrow payment pending"}
                    </small>
                  </span>
                  <div>
                    {next && (
                      <label className="fulfillment-status-control">
                        Next status
                        <select
                          value={nextStatuses[order.id] ?? next[0]}
                          disabled={readOnly || savingId === order.id}
                          onChange={(event) =>
                            setNextStatuses((current) => ({
                              ...current,
                              [order.id]: event.target.value,
                            }))
                          }
                        >
                          <option value="" disabled>Choose next status</option>
                          <option value={next[0]}>{STATUS_LABELS[next[0]]}</option>
                        </select>
                      </label>
                    )}
                    <button
                      type="button"
                      className="marketplace-button secondary"
                      onClick={() => openWaybill(order)}
                    >
                      <Printer size={15} /> Waybill
                    </button>
                    {next && (
                      <button
                        type="button"
                        className="marketplace-button primary"
                        disabled={readOnly || savingId === order.id}
                        onClick={() => advance(order)}
                      >
                        <PackageCheck size={15} />
                        {savingId === order.id ? "Saving…" : "Save status"}
                        <ArrowRight size={14} />
                      </button>
                    )}
                    {terminal && <span className="fulfillment-terminal"><Truck size={14} /> Complete</span>}
                  </div>
                </footer>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="marketplace-empty">Orders containing your products will appear here.</p>
      )}
      {slip && (
        <div className="fulfillment-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSlip(null);
        }}>
          <section className="fulfillment-waybill" role="dialog" aria-modal="true" aria-labelledby="fulfillment-waybill-title">
            <header>
              <div>
                <span className="marketplace-eyebrow">MAISON MUSE · SELLER DISPATCH</span>
                <h2 id="fulfillment-waybill-title">Package waybill</h2>
              </div>
              <button type="button" className="marketplace-button secondary" onClick={() => setSlip(null)}>Close</button>
            </header>
            <div className="fulfillment-label-print">
              <div className="fulfillment-label-brand">MAISON MUSE <span>ORDER DISPATCH</span></div>
              <div className="fulfillment-label-order"><strong>{slip.order_number}</strong><span>{slip.tracking_id}</span></div>
              <p><b>DELIVER TO</b><br />{slip.customer.name}<br />{slip.customer.phone}<br />{slip.customer.address}</p>
              <p><b>COURIER</b><br />{slip.courier_name || "Assign at drop-off"} · {slip.tracking_number || "Tracking reference pending"}</p>
              <div className="fulfillment-label-lines">
                {slip.items.map((item, index) => (
                  <span key={`${item.product_id}-${index}`}>{item.quantity} × {item.product_name}{item.variant ? ` · ${item.variant}` : ""}</span>
                ))}
              </div>
              <img src={slip.qrCode} alt={`QR code for ${slip.tracking_id}`} />
              <small>Scan to check fulfillment status</small>
            </div>
            <button type="button" className="marketplace-button primary" onClick={() => window.print()}>
              <Printer size={15} /> Print waybill
            </button>
          </section>
        </div>
      )}
    </section>
  );
}

export default OrderFulfillment;
