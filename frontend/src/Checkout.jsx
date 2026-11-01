import { useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  LockKeyhole,
  MapPin,
  Smartphone,
  Truck,
  X,
} from "lucide-react";
import { formatKsh } from "./data/currency.js";
import ProductImage from "./components/ProductImage.jsx";

const initialContact = {
  name: "",
  phone: "",
  address: "",
};

export const FREE_SHIPPING_THRESHOLD = 5000;
const SHIPPING_FEE = 250;

function validateContact(contact) {
  const errors = {};
  const normalizedPhone = contact.phone.replace(/\D/g, "");
  const nameParts = contact.name.trim().split(/\s+/).filter(Boolean);

  if (nameParts.length < 2 || nameParts.some((part) => part.length < 2)) {
    errors.name = "Enter your first and last name.";
  }
  if (normalizedPhone.length < 7 || normalizedPhone.length > 15) {
    errors.phone = "Enter a valid phone number with 7–15 digits.";
  }
  if (contact.address.trim().length < 8) {
    errors.address = "Enter a complete delivery address.";
  }

  return errors;
}

function Checkout({ items, subtotal, onClose, onPlaceOrder }) {
  const [step, setStep] = useState(1);
  const [contact, setContact] = useState(initialContact);
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const shipping = subtotal >= FREE_SHIPPING_THRESHOLD ? 0 : SHIPPING_FEE;
  const tax = Math.round(subtotal * 0.08 * 100) / 100;
  const total = subtotal + shipping + tax;

  const updateContact = (event) => {
    const { name, value } = event.target;
    setContact((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: undefined }));
  };

  const continueToPayment = (event) => {
    event.preventDefault();
    const contactErrors = validateContact(contact);
    setErrors(contactErrors);
    if (Object.keys(contactErrors).length === 0) setStep(2);
  };

  const placeOrder = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const payment = await onPlaceOrder({
        customer: contact,
        items,
      });
      const redirectUrl = new URL(payment.redirect_url);
      if (
        redirectUrl.protocol !== "https:" ||
        !["cybqa.pesapal.com", "pay.pesapal.com"].includes(redirectUrl.hostname)
      ) {
        throw new Error("Pesapal returned an invalid secure checkout link.");
      }
      window.location.assign(redirectUrl.href);
    } catch (error) {
      setErrors({ submit: error.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const fieldClass = (name) =>
    `checkout-input ${errors[name] ? "has-error" : ""}`;

  const renderError = (name) =>
    errors[name] ? (
      <span className="checkout-field-error" id={`${name}-error`}>
        {errors[name]}
      </span>
    ) : null;

  return createPortal(
    <div className="checkout-layer">
      <div className="checkout-page">
        <header className="checkout-header">
          <a className="wordmark checkout-wordmark" href="#" aria-label="Maison Muse home">
            maison <span>muse</span><i aria-hidden="true">.</i>
          </a>
          <div className="checkout-secure-note">
            <LockKeyhole size={14} /> Secure checkout
          </div>
          <button
            className="checkout-exit"
            type="button"
            aria-label="Return to your bag"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>

        <div className="checkout-progress" aria-label={`Checkout step ${step} of 2`}>
            <div className={`checkout-progress-step ${step >= 1 ? "is-current" : ""}`}>
              <span>{step > 1 ? <Check size={13} /> : "01"}</span>
              <div><strong>Delivery</strong><small>Contact & address</small></div>
            </div>
            <span className={`checkout-progress-line ${step > 1 ? "is-complete" : ""}`} />
            <div className={`checkout-progress-step ${step >= 2 ? "is-current" : ""}`}>
              <span>02</span>
              <div><strong>Payment</strong><small>Secure Pesapal checkout</small></div>
            </div>
        </div>
            <div className="checkout-intro">
              <div className="checkout-eyebrow">A FEW LITTLE DETAILS</div>
              <h1>{step === 1 ? <>Let’s get it <em>to you.</em></> : <>Make it a <em>good one.</em></>}</h1>
              <p>
                {step === 1
                  ? "Where should we send your feel-good finds?"
                  : "You’ll complete your payment securely with Pesapal."}
              </p>
            </div>

            <div className="checkout-layout">
              <main className="checkout-form-panel">
                {step === 1 ? (
                  <form onSubmit={continueToPayment} noValidate>
                    <section className="checkout-form-section" aria-labelledby="contact-heading">
                      <div className="checkout-section-heading">
                        <span className="checkout-section-icon"><Smartphone size={16} /></span>
                        <div>
                          <h2 id="contact-heading">Contact information</h2>
                          <p>So we can keep you in the loop.</p>
                        </div>
                      </div>

                      <div className="checkout-field">
                        <label htmlFor="checkout-name">Full name</label>
                        <input
                          className={fieldClass("name")}
                          id="checkout-name"
                          name="name"
                          autoComplete="name"
                          placeholder="Your first and last name"
                          value={contact.name}
                          onChange={updateContact}
                          aria-invalid={Boolean(errors.name)}
                          aria-describedby={errors.name ? "name-error" : undefined}
                        />
                        {renderError("name")}
                      </div>
                      <div className="checkout-field">
                        <label htmlFor="checkout-phone">Phone number</label>
                        <input
                          className={fieldClass("phone")}
                          id="checkout-phone"
                          name="phone"
                          type="tel"
                          autoComplete="tel"
                          inputMode="tel"
                          placeholder="+1 (555) 000-0000"
                          value={contact.phone}
                          onChange={updateContact}
                          aria-invalid={Boolean(errors.phone)}
                          aria-describedby={errors.phone ? "phone-error" : undefined}
                        />
                        {renderError("phone")}
                      </div>
                    </section>

                    <section className="checkout-form-section" aria-labelledby="address-heading">
                      <div className="checkout-section-heading">
                        <span className="checkout-section-icon"><MapPin size={16} /></span>
                        <div>
                          <h2 id="address-heading">Delivery address</h2>
                          <p>We’ll bring your good stuff right to your door.</p>
                        </div>
                      </div>
                      <div className="checkout-field">
                        <label htmlFor="checkout-address">Street address</label>
                        <textarea
                          className={`${fieldClass("address")} checkout-textarea`}
                          id="checkout-address"
                          name="address"
                          autoComplete="street-address"
                          placeholder="Street, building, apartment, city, postal code"
                          rows={3}
                          value={contact.address}
                          onChange={updateContact}
                          aria-invalid={Boolean(errors.address)}
                          aria-describedby={errors.address ? "address-error" : undefined}
                        />
                        {renderError("address")}
                      </div>
                    </section>

                    <button className="checkout-submit" type="submit">
                      Continue to Payment <ArrowRight size={16} />
                    </button>
                  </form>
                ) : (
                  <form onSubmit={placeOrder} noValidate>
                    <button
                      className="checkout-back-button"
                      type="button"
                      onClick={() => {
                        setErrors({});
                        setStep(1);
                      }}
                    >
                      <ArrowLeft size={14} /> Back to delivery
                    </button>

                    <section className="checkout-form-section payment-section" aria-labelledby="payment-heading">
                      <div className="checkout-section-heading">
                        <span className="checkout-section-icon"><LockKeyhole size={16} /></span>
                        <div>
                          <h2 id="payment-heading">Pay securely with Pesapal</h2>
                          <p>Choose an available payment method on Pesapal’s secure page.</p>
                        </div>
                      </div>
                      <div className="payment-option is-selected">
                        <span className="payment-option-icon"><LockKeyhole size={17} /></span>
                        <span className="payment-option-copy">
                          <strong>Protected payment</strong>
                          <small>Your payment details are entered directly on Pesapal.</small>
                        </span>
                        <Check size={16} aria-hidden="true" />
                      </div>
                      <p className="payment-provider-note">
                        Maison Muse never collects or stores your card or mobile-wallet credentials.
                      </p>
                    </section>

                    {errors.submit && (
                      <p className="checkout-field-error" role="alert">
                        {errors.submit}
                      </p>
                    )}
                    <button className="checkout-submit" type="submit" disabled={isSubmitting}>
                      {isSubmitting
                        ? "Connecting to Pesapal…"
                        : `Continue to Pesapal · ${formatKsh(total)}`}
                      {!isSubmitting && <ArrowRight size={16} />}
                    </button>
                  </form>
                )}
              </main>

              <aside className="checkout-summary" aria-labelledby="summary-heading">
                <div className="checkout-summary-title">
                  <h2 id="summary-heading">Your little treats</h2>
                  <span>{items.reduce((count, item) => count + item.quantity, 0)} items</span>
                </div>
                <div className="checkout-summary-items">
                  {items.map((item) => (
                    <div className="checkout-summary-item" key={item.cartKey}>
                      <div className="checkout-summary-image">
                        <ProductImage src={item.image} alt="" />
                        <span>{item.quantity}</span>
                      </div>
                      <div className="checkout-summary-item-copy">
                        <strong>{item.name}</strong>
                        <span>{item.variant ? `Size ${item.variant} · ` : ""}{item.detail}</span>
                      </div>
                      <strong className="checkout-summary-item-price">
                        {formatKsh(item.price * item.quantity)}
                      </strong>
                    </div>
                  ))}
                </div>
                <div className="checkout-summary-totals">
                  <div><span>Subtotal</span><strong>{formatKsh(subtotal)}</strong></div>
                  <div className="summary-shipping-label">
                    <span><Truck size={14} /> Shipping</span>
                    <strong>{shipping === 0 ? "Complimentary" : formatKsh(shipping)}</strong>
                  </div>
                  <div>
                    <span>Estimated tax <small>(8%)</small></span>
                    <strong>{formatKsh(tax)}</strong>
                  </div>
                  <div className="checkout-grand-total">
                    <span>Total</span><strong>{formatKsh(total)}</strong>
                  </div>
                </div>
                <div className="checkout-shipping-promo">
                  <span>✳</span>
                  {shipping === 0
                    ? "You’ve unlocked complimentary shipping."
                    : `Add ${formatKsh(FREE_SHIPPING_THRESHOLD - subtotal)} for complimentary shipping.`}
                </div>
                <div className="checkout-summary-footnote">
                  <LockKeyhole size={13} />
                  Your order total is calculated securely by Maison Muse.
                </div>
              </aside>
            </div>
      </div>
    </div>,
    document.body,
  );
}

export default Checkout;
