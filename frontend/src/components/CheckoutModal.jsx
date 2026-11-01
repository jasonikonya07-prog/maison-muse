import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, Check, MapPin, ShieldCheck, Smartphone, Store, X } from "lucide-react";
import { formatKsh } from "../data/currency.js";
import { useFeatures } from "../context/FeatureContext.jsx";

const CITIES = ["Nairobi", "Mombasa", "Nakuru", "Kisumu", "Eldoret", "Thika", "Other"];
const DELIVERY_FEE = 250;
const FREE_DELIVERY_THRESHOLD = 5000;

const initialForm = {
  name: "",
  phone: "",
  city: "Nairobi",
  address: "",
  deliveryNotes: "",
  mpesaPhone: "",
};

function getVendor(item) {
  const seller = item.seller ?? item.vendor ?? null;
  return {
    id: seller?.id ?? item.sellerId ?? item.seller_id ?? "maison-muse",
    name: seller?.storeName ?? seller?.store_name ?? item.sellerName ?? "Maison Muse",
    slug: seller?.storeSlug ?? seller?.store_slug ?? "",
    verified: Boolean(seller),
  };
}

function CheckoutModal({ items, subtotal, onClose, onFinish, onPlaceOrder }) {
  const { verifiedSellerBadge } = useFeatures();
  const [form, setForm] = useState(initialForm);
  const [showPushPrompt, setShowPushPrompt] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState("");

  const groups = useMemo(() => {
    const sellers = new Map();
    items.forEach((item) => {
      const vendor = getVendor(item);
      if (!sellers.has(vendor.id)) sellers.set(vendor.id, { ...vendor, items: [], subtotal: 0 });
      const group = sellers.get(vendor.id);
      group.items.push(item);
      group.subtotal += item.price * item.quantity;
    });
    return [...sellers.values()];
  }, [items]);

  const shipping = subtotal >= FREE_DELIVERY_THRESHOLD ? 0 : DELIVERY_FEE;
  const tax = Math.round(subtotal * 0.08 * 100) / 100;
  const total = subtotal + shipping + tax;

  const updateForm = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
    setError("");
  };

  const submitCheckout = async () => {
    setError("");
    setIsSubmitting(true);
    try {
      const result = await onPlaceOrder({
        customer: {
          name: form.name,
          phone: form.phone,
          address: form.address,
        },
        items,
        city: form.city,
        deliveryNotes: form.deliveryNotes,
        mpesaPhone: form.mpesaPhone,
      });
      setReceipt(result);
      setShowPushPrompt(false);
    } catch (submitError) {
      setError(submitError.message);
      setShowPushPrompt(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div className="multi-checkout-backdrop">
      <section
        className="multi-checkout-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="multi-checkout-title"
      >
        <header className="multi-checkout-header">
          <a className="wordmark" href="/" aria-label="Maison Muse home">maison <span>muse</span><i>.</i></a>
          <span><ShieldCheck size={15} /> Demo secure checkout</span>
          <button type="button" className="checkout-exit" aria-label="Close checkout" onClick={onClose}><X size={18} /></button>
        </header>

        {receipt ? (
          <div className="multi-checkout-success">
            <span className="multi-checkout-success-icon"><Check size={23} /></span>
            <p className="checkout-eyebrow">SIMULATED M-PESA PAYMENT COMPLETE</p>
            <h1 id="multi-checkout-title">Your order is <em>confirmed.</em></h1>
            <p className="multi-checkout-success-copy">
              A simulated STK prompt was approved for {form.mpesaPhone}. No real payment was sent.
            </p>
            <div className="multi-checkout-reference">
              <span>MASTER TRACKING ID</span><strong>{receipt.master_tracking_id ?? receipt.order_number}</strong>
              <span>M-PESA SIMULATION REFERENCE</span><strong>{receipt.transaction_reference}</strong>
            </div>
            <div className="multi-checkout-suborders">
              <h2>Vendor order split</h2>
              {(receipt.sub_orders ?? []).map((order) => (
                <article key={order.sub_order_id}>
                  <div><Store size={15} /><strong>{order.store_name}</strong></div>
                  <small>Sub-order #{order.sub_order_id} · {order.status}</small>
                  <p>Gross {formatKsh(order.gross_amount)} − commission {formatKsh(order.commission_amount)}</p>
                  <strong className="multi-checkout-net">Vendor escrow {formatKsh(order.net_amount)}</strong>
                </article>
              ))}
            </div>
            <button type="button" className="checkout-submit" onClick={() => onFinish(receipt)}>
              Continue shopping <ArrowRight size={16} />
            </button>
          </div>
        ) : (
          <>
            <div className="multi-checkout-title">
              <p className="checkout-eyebrow">MAISON MUSE MARKETPLACE</p>
              <h1 id="multi-checkout-title">Your edit, <em>on its way.</em></h1>
              <p>One checkout, with each boutique fulfilled separately.</p>
            </div>
            <div className="multi-checkout-grid">
              <form className="multi-checkout-form" onSubmit={(event) => { event.preventDefault(); setShowPushPrompt(true); }}>
                <section className="multi-checkout-section">
                  <h2><Smartphone size={17} /> Buyer details</h2>
                  <div className="multi-checkout-fields">
                    <label>Full name<input name="name" autoComplete="name" required minLength="4" value={form.name} onChange={updateForm} placeholder="First and last name" /></label>
                    <label>Contact phone<input name="phone" type="tel" autoComplete="tel" required minLength="7" value={form.phone} onChange={updateForm} placeholder="0712 345 678" /></label>
                  </div>
                </section>
                <section className="multi-checkout-section">
                  <h2><MapPin size={17} /> Delivery address</h2>
                  <div className="multi-checkout-fields">
                    <label>City / location<select name="city" value={form.city} onChange={updateForm}>{CITIES.map((city) => <option key={city}>{city}</option>)}</select></label>
                    <label className="multi-checkout-wide">Street address<input name="address" autoComplete="street-address" required minLength="8" value={form.address} onChange={updateForm} placeholder="Street, building, apartment" /></label>
                    <label className="multi-checkout-wide">Delivery notes <span>(optional)</span><textarea name="deliveryNotes" rows="2" maxLength="500" value={form.deliveryNotes} onChange={updateForm} placeholder="Landmark, gate instructions, or preferred time" /></label>
                  </div>
                </section>
                <section className="multi-checkout-section">
                  <h2><Smartphone size={17} /> M-Pesa payment</h2>
                  <label className="multi-checkout-mpesa">M-Pesa phone number<input name="mpesaPhone" type="tel" inputMode="tel" required minLength="7" value={form.mpesaPhone} onChange={updateForm} placeholder="0712345678" /></label>
                  <p className="multi-checkout-demo-note">Demo STK Push only. This workflow records a simulated payment and does not contact Safaricom or move money.</p>
                </section>
                {error && <p className="checkout-field-error" role="alert">{error}</p>}
                <button className="checkout-submit" type="submit">Pay via M-Pesa (STK Push) · {formatKsh(total)} <ArrowRight size={16} /></button>
              </form>

              <aside className="multi-checkout-summary">
                <h2>Your cart <span>{items.reduce((count, item) => count + item.quantity, 0)} items</span></h2>
                {groups.map((group) => (
                  <section className="multi-checkout-vendor" key={group.id}>
                    <h3>{verifiedSellerBadge && group.verified && <ShieldCheck size={14} />} {group.name}</h3>
                    {group.items.map((item) => (
                      <article key={item.cartKey}>
                        <img src={item.image} alt="" />
                        <div><strong>{item.name}</strong><small>{item.quantity} × {formatKsh(item.price)}</small></div>
                        <b>{formatKsh(item.price * item.quantity)}</b>
                      </article>
                    ))}
                    <p><span>Boutique subtotal</span><strong>{formatKsh(group.subtotal)}</strong></p>
                  </section>
                ))}
                <div className="multi-checkout-totals">
                  <p><span>Subtotal</span><strong>{formatKsh(subtotal)}</strong></p>
                  <p><span>Delivery</span><strong>{shipping ? formatKsh(shipping) : "Complimentary"}</strong></p>
                  <p><span>Estimated tax</span><strong>{formatKsh(tax)}</strong></p>
                  <p className="multi-checkout-total"><span>Total</span><strong>{formatKsh(total)}</strong></p>
                </div>
              </aside>
            </div>
          </>
        )}

        {showPushPrompt && !receipt && (
          <div className="multi-checkout-prompt-backdrop">
            <section className="multi-checkout-prompt" role="alertdialog" aria-modal="true" aria-labelledby="mpesa-prompt-title">
              <button type="button" aria-label="Cancel payment" onClick={() => setShowPushPrompt(false)}><X size={17} /></button>
              <span className="multi-checkout-prompt-icon"><Smartphone size={22} /></span>
              <p className="checkout-eyebrow">SIMULATED STK PUSH</p>
              <h2 id="mpesa-prompt-title">Payment request ready</h2>
              <p>A demo M-Pesa prompt for <strong>{form.mpesaPhone}</strong> will be simulated for <strong>{formatKsh(total)}</strong>.</p>
              {error && <p className="checkout-field-error" role="alert">{error}</p>}
              <button type="button" className="checkout-submit" disabled={isSubmitting} onClick={submitCheckout}>
                {isSubmitting ? "Confirming demo payment…" : "Confirm demo payment"}
              </button>
              <small>No payment will be sent to a mobile-money provider.</small>
            </section>
          </div>
        )}
      </section>
    </div>,
    document.body,
  );
}

export default CheckoutModal;
