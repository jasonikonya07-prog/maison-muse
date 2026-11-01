import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  MessageCircle,
  Minus,
  Phone,
  Plus,
  ShieldCheck,
  ShoppingBag,
  X,
} from "lucide-react";
import { formatKsh } from "../data/currency.js";
import { getFarmerWhatsAppUrl } from "../data/agriFarm.js";
import { useFeatures } from "../context/FeatureContext.jsx";
import {
  fetchBuyerSellerConversation,
  replyToBuyerSellerConversation,
  startBuyerSellerConversation,
} from "../services/api.js";

function ProductModal({ product, availableStock, onClose, onAddToCart, onBuyNow }) {
  const { verifiedSellerBadge, whatsappDirectBypass } = useFeatures();
  const [quantity, setQuantity] = useState(1);
  const [addedToCart, setAddedToCart] = useState(false);
  const [inquiryName, setInquiryName] = useState("");
  const [inquiryBody, setInquiryBody] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [conversationMessages, setConversationMessages] = useState([]);
  const [inquiryError, setInquiryError] = useState("");
  const [sendingInquiry, setSendingInquiry] = useState(false);
  const sellerName = product.seller?.storeName ?? product.seller_name;
  const sellerSlug = product.seller?.storeSlug ?? product.seller_slug;
  const sellerPhone =
    product.seller?.businessPhone ??
    product.seller?.whatsappPhone ??
    product.seller_phone;
  const whatsappPhone = product.seller?.whatsappPhone || sellerPhone;
  const verified = product.seller?.verified ?? product.seller_verified;
  const isInStock = availableStock > 0 && !product.seller?.holidayMode;
  const specifications = Array.isArray(product.features)
    ? product.features
    : Array.isArray(product.highlights)
      ? product.highlights
      : Object.entries(product.details ?? {})
          .filter(([key]) => key !== "availableSizes")
          .map(([key, value]) => `${key.replace(/([A-Z])/g, " $1")}: ${value}`);
  const images = product.gallery?.length ? product.gallery : [product.image];
  const whatsappDigits = whatsappPhone?.replace(/\D/g, "").replace(/^0/, "254");
  const farmerWhatsAppUrl = product.is_agri_product && whatsappDirectBypass
    ? getFarmerWhatsAppUrl(product)
    : "";

  const handleAddToCart = () => {
    onAddToCart(product, quantity);
    setAddedToCart(true);
  };

  useEffect(() => {
    if (!conversationId) return undefined;
    let active = true;
    const refresh = async () => {
      try {
        const messages = await fetchBuyerSellerConversation(conversationId);
        if (active) setConversationMessages(messages);
      } catch (error) {
        if (active) setInquiryError(error.message);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [conversationId]);

  async function sendInquiry(event) {
    event.preventDefault();
    setSendingInquiry(true);
    setInquiryError("");
    try {
      if (conversationId) {
        await replyToBuyerSellerConversation(conversationId, inquiryBody);
      } else {
        const conversation = await startBuyerSellerConversation({
          product_id: product.id,
          customer_name: inquiryName,
          body: inquiryBody,
        });
        setConversationId(conversation.conversation_id);
      }
      setInquiryBody("");
    } catch (error) {
      setInquiryError(error.message);
    } finally {
      setSendingInquiry(false);
    }
  }

  return createPortal(
    <div className="product-modal-layer">
      <button
        className="product-modal-backdrop"
        type="button"
        aria-label={`Close ${product.name} details`}
        onClick={onClose}
      />
      <section
        className="product-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-modal-title"
      >
        <button
          className="product-modal-close"
          type="button"
          aria-label="Close product details"
          onClick={onClose}
          autoFocus
        >
          <X size={19} />
        </button>
        <div className="product-modal-gallery">
          <div className="product-modal-image">
            <img src={images[0]} alt={product.name} />
            <span className={`stock-badge ${isInStock ? "is-available" : "is-sold-out"}`}>
              <span />
              {isInStock ? `${availableStock} available` : "Sold out"}
            </span>
          </div>
        </div>
        <div className="product-modal-details">
          <div className="product-modal-category">{product.category}</div>
          <h2 id="product-modal-title">{product.name}</h2>
          <p className="product-modal-subtitle">{product.detail}</p>
          {sellerName && (
            <>
              {sellerSlug ? (
                <Link
                  className="product-seller-attribution modal-seller-attribution"
                  to={`/boutiques/${encodeURIComponent(sellerSlug)}`}
                  onClick={onClose}
                >
                  Sold &amp; fulfilled by {sellerName}
                  {verifiedSellerBadge && verified && <ShieldCheck size={14} aria-label="Verified seller" />}
                </Link>
              ) : (
                <p className="product-seller-attribution modal-seller-attribution">
                  Sold &amp; fulfilled by {sellerName}
                  {verifiedSellerBadge && verified && <ShieldCheck size={14} aria-label="Verified seller" />}
                </p>
              )}
              {product.sellerId && (
                <section className="product-seller-inquiry">
                  <h3>Ask the boutique</h3>
                  <p>Message the seller about sizing, custom requests, or delivery details.</p>
                  {conversationId ? (
                    <div className="product-inquiry-thread" aria-live="polite">
                      {conversationMessages.map((message, index) => (
                        <p key={`${index}-${message.created_at}`}><strong>{message.sender_name}:</strong> {message.body}</p>
                      ))}
                      <form onSubmit={sendInquiry}>
                        <label className="visually-hidden" htmlFor="buyer-inquiry-followup">Your message</label>
                        <textarea id="buyer-inquiry-followup" rows="2" maxLength="2000" required value={inquiryBody} onChange={(event) => setInquiryBody(event.target.value)} />
                        <button className="marketplace-button secondary" type="submit" disabled={sendingInquiry}>{sendingInquiry ? "Sending…" : "Send message"}</button>
                      </form>
                    </div>
                  ) : (
                    <form onSubmit={sendInquiry}>
                      <label>Your name<input required minLength="2" maxLength="120" value={inquiryName} onChange={(event) => setInquiryName(event.target.value)} /></label>
                      <label>Message<textarea rows="3" maxLength="2000" required value={inquiryBody} onChange={(event) => setInquiryBody(event.target.value)} /></label>
                      <button className="marketplace-button secondary" type="submit" disabled={sendingInquiry}>{sendingInquiry ? "Sending…" : "Message seller"}</button>
                    </form>
                  )}
                  {inquiryError && <p className="marketplace-error" role="alert">{inquiryError}</p>}
                  <small>Keep this product page open to see the seller's reply. Messages are not sent by email or SMS.</small>
                </section>
              )}
              {sellerPhone && (
                <p className="product-seller-contact modal-seller-contact">
                  <Phone size={13} aria-hidden="true" />
                  Support / WhatsApp: {sellerPhone}
                  <a href={`tel:${sellerPhone.replace(/[^\d+]/g, "")}`} onClick={onClose}>
                    Call seller
                  </a>
                  {whatsappDigits && (
                    <a
                      href={`https://wa.me/${whatsappDigits}`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Chat with ${sellerName} on WhatsApp`}
                      onClick={onClose}
                    >
                      <MessageCircle size={15} />
                    </a>
                  )}
                </p>
              )}
            </>
          )}
          <div className="product-modal-price">{formatKsh(product.price)}</div>
          <p className="product-modal-description">{product.description}</p>
          {specifications.length > 0 && (
            <div className="product-feature-block">
              <h3>Specifications</h3>
              <ul>
                {specifications.map((feature, index) => (
                  <li key={`${index}-${feature}`}>{feature}</li>
                ))}
              </ul>
            </div>
          )}
          {!product.is_agri_product && <div className="modal-purchase">
            <div className="modal-quantity-picker" aria-label="Quantity">
              <button
                type="button"
                aria-label="Decrease quantity"
                disabled={quantity <= 1}
                onClick={() => setQuantity((current) => Math.max(1, current - 1))}
              >
                <Minus size={14} />
              </button>
              <span aria-live="polite">{quantity}</span>
              <button
                type="button"
                aria-label="Increase quantity"
                disabled={quantity >= availableStock}
                onClick={() =>
                  setQuantity((current) => Math.min(availableStock, current + 1))
                }
              >
                <Plus size={14} />
              </button>
            </div>
            <span className="modal-line-price">{formatKsh(product.price * quantity)}</span>
          </div>}
          {product.is_agri_product ? (
            <div className="product-modal-actions">
              {farmerWhatsAppUrl ? (
                <a
                  className="modal-add-button is-agri-contact"
                  href={farmerWhatsAppUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageCircle size={17} />
                  Contact Farmer on WhatsApp
                  <span>{formatKsh(product.price)}</span>
                </a>
              ) : (
                <p className="marketplace-error" role="alert">
                  {whatsappDirectBypass
                    ? "The farmer has not provided a WhatsApp contact for this listing."
                    : "Direct farmer contact is currently unavailable."}
                </p>
              )}
            </div>
          ) : <div className="product-modal-actions">
            <button
              className="modal-add-button"
              type="button"
              disabled={!isInStock}
              onClick={handleAddToCart}
            >
              <ShoppingBag size={16} />
              {isInStock ? "Add to Cart" : "Sold Out"}
              <span>{formatKsh(product.price * quantity)}</span>
            </button>
            <button
              className="modal-buy-button"
              type="button"
              disabled={!isInStock}
              onClick={() => onBuyNow(product, quantity, "")}
            >
              Buy Now <ArrowRight size={16} />
            </button>
          </div>}
          {addedToCart && !product.is_agri_product && (
            <p className="modal-added-message" role="status">
              <Check size={14} /> Added to your bag.
            </p>
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}

export default ProductModal;
