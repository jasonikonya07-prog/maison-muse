import { useEffect, useState } from "react";
import {
  BadgeCheck,
  Building2,
  MapPin,
  MessageCircle,
  Phone,
  ShieldAlert,
  ShieldCheck,
  Star,
  X,
} from "lucide-react";
import { fetchSellerInspection } from "../services/api.js";
import "./SellerInspectorModal.css";

function SellerInspectorModal({
  isOpen = true,
  onClose = () => {},
  initialQuery = "",
  embedded = false,
}) {
  const [query, setQuery] = useState(initialQuery);
  const [dossier, setDossier] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    if (!isOpen || query.trim().length < 2) {
      setDossier(null);
      setLoading(false);
      setError("");
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError("");
    const timer = window.setTimeout(async () => {
      try {
        const result = await fetchSellerInspection(query.trim());
        if (active) setDossier(result);
      } catch (lookupError) {
        if (active) {
          setDossier(null);
          setError(lookupError.message);
        }
      } finally {
        if (active) setLoading(false);
      }
    }, 350);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [isOpen, query]);

  if (!isOpen) return null;

  const registeredDate = dossier?.registered_date
    ? new Date(dossier.registered_date).toLocaleDateString(undefined, {
        month: "long",
        year: "numeric",
      })
    : "";
  const rating = Number(dossier?.rating ?? 0);

  return (
    <div className={`seller-inspector-shell ${embedded ? "embedded" : "overlay"}`} role={embedded ? undefined : "presentation"} onMouseDown={(event) => {
      if (!embedded && event.target === event.currentTarget) onClose();
    }}>
      <section className="seller-inspector-dialog" role="dialog" aria-modal={!embedded} aria-labelledby="seller-inspector-title">
        <header className="seller-inspector-header">
          <div>
            <span className="seller-inspector-eyebrow"><ShieldCheck size={14} /> SELLER TRUST CENTER</span>
            <h2 id="seller-inspector-title">Inspect a seller</h2>
            <p>Review official store identity, fulfillment history, and verified buyer feedback.</p>
          </div>
          {!embedded && (
            <button type="button" className="seller-inspector-close" aria-label="Close seller inspector" onClick={onClose}>
              <X size={19} />
            </button>
          )}
        </header>
        <label className="seller-inspector-search">
          <span>Seller name or store ID</span>
          <input
            type="search"
            autoFocus={!embedded}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search a boutique or vendor"
          />
          {loading && <small>Checking official seller records…</small>}
        </label>
        {error && <p className="seller-inspector-error" role="alert">{error}</p>}
        {!dossier && !loading && !error && (
          <p className="seller-inspector-empty">Enter at least two characters to look up a store.</p>
        )}
        {dossier && (
          <div className="seller-inspector-dossier">
            <section className="seller-inspector-store">
              <div className={`seller-inspector-shield ${dossier.is_verified ? "verified" : "unverified"}`}>
                {dossier.is_verified ? <BadgeCheck size={22} /> : <ShieldAlert size={22} />}
              </div>
              <div className="seller-inspector-store-title">
                <span className={dossier.is_verified ? "verified-text" : "unverified-text"}>
                  {dossier.is_verified ? "VERIFIED MERCHANT" : dossier.verification_status === "SUSPENDED" ? "SUSPENDED" : "UNVERIFIED / UNDER REVIEW"}
                </span>
                <h3>{dossier.store_name}</h3>
                <small>Registered member since {registeredDate}</small>
              </div>
            </section>
            <div className="seller-inspector-facts">
              <article><Building2 size={16} /><span><small>Industry</small><strong>{dossier.business_type || dossier.business_category || "Not provided"}</strong></span></article>
              <article><MapPin size={16} /><span><small>Registered hub</small><strong>{dossier.city || "Not provided"}</strong></span></article>
              <article><Phone size={16} /><span><small>Official phone</small><a href={`tel:${dossier.phone_number}`}>{dossier.phone_number || "Not provided"}</a></span></article>
              <article><MessageCircle size={16} /><span><small>WhatsApp line</small><a href={dossier.whatsapp_number ? `https://wa.me/${dossier.whatsapp_number.replace(/\D/g, "")}` : undefined}>{dossier.whatsapp_number || "Not provided"}</a></span></article>
            </div>
            <section className="seller-inspector-trust">
              <header><div><ShieldCheck size={17} /><h3>Safety &amp; fulfillment</h3></div><strong>{dossier.trust_score}% trust score</strong></header>
              <div className="seller-inspector-trust-grid">
                <span><small>Escrow fulfillment</small><strong>{dossier.fulfillment_rate}%</strong></span>
                <span><small>Paid orders</small><strong>{dossier.total_sales_count.toLocaleString()}</strong></span>
                <span><small>Risk &amp; compliance</small><strong>{dossier.admin_flags.join(" · ")}</strong></span>
              </div>
            </section>
            <section className="seller-inspector-reviews">
              <header>
                <div><Star size={17} /><h3>Verified buyer reviews</h3></div>
                <strong>{rating.toFixed(1)} / 5 <small>· {dossier.review_count} verified</small></strong>
              </header>
              {dossier.reviews.length ? (
                <div className="seller-inspector-review-list">
                  {dossier.reviews.map((review) => (
                    <article key={`${review.order_number}-${review.created_at}`}>
                      <div><strong>{review.buyer_name}</strong><span><Star size={12} fill="currentColor" /> {review.rating}/5</span></div>
                      <p>{review.comment}</p>
                      <small>Verified order · {review.order_number} · {new Date(review.created_at).toLocaleDateString()}</small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="seller-inspector-no-reviews">No verified buyer reviews have been recorded yet.</p>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

export default SellerInspectorModal;
