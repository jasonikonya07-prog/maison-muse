import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, MessageCircle, Sprout } from "lucide-react";
import { formatKsh } from "../data/currency.js";
import { useFeatures } from "../context/FeatureContext.jsx";
import {
  AGRI_FARM_CATEGORIES,
  getFarmerWhatsAppUrl,
} from "../data/agriFarm.js";
import { fetchProducts } from "../services/api.js";
import "./AgriFarmHub.css";

function AgriFarmHub({ embedded = false }) {
  const { whatsappDirectBypass } = useFeatures();
  const [category, setCategory] = useState(AGRI_FARM_CATEGORIES[0].value);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchProducts({ category, signal: controller.signal, limit: 100 })
      .then((items) => setProducts(items.filter((item) => item.is_agri_product)))
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setProducts([]);
          setError(loadError.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [category]);

  return (
    <section className={`agri-hub ${embedded ? "agri-hub-embedded" : ""}`}>
      {!embedded && <header className="agri-hub-header">
        <Link className="agri-hub-brand" to="/">
          <Sprout size={24} aria-hidden="true" />
          <span>Maison Muse <strong>Farm Direct</strong></span>
        </Link>
        <Link className="agri-hub-back" to="/shop">
          <ArrowLeft size={15} /> Back to marketplace
        </Link>
      </header>}

      <section className="agri-hub-hero">
        <span className="agri-hub-eyebrow">AGRI-FARM &amp; LIVESTOCK MARKETPLACE</span>
        <h1>Farm Direct</h1>
        <p>Find livestock, poultry and farm essentials from local sellers.</p>
        <div className="agri-hub-notice">
          Contact farmers directly on WhatsApp to confirm availability, animal records,
          product directions and collection or delivery details. Farm Direct listings
          are not eligible for Maison Muse checkout or escrow.
        </div>
      </section>

      <nav className="agri-hub-tabs" aria-label="Farm product categories">
        {AGRI_FARM_CATEGORIES.map((item) => (
          <button
            type="button"
            className={category === item.value ? "active" : ""}
            aria-pressed={category === item.value}
            key={item.value}
            onClick={() => setCategory(item.value)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {error && <p className="agri-hub-error" role="alert">{error}</p>}
      <section className="agri-hub-products" aria-live="polite" aria-busy={loading}>
        {loading ? (
          <p className="agri-hub-empty">Loading farm listings…</p>
        ) : products.length ? (
          products.map((product) => {
            const whatsappUrl = getFarmerWhatsAppUrl(product);
            return (
              <article className="agri-product-card" key={product.id}>
                <img src={product.image} alt={product.name} loading="lazy" />
                <div className="agri-product-content">
                  <span className="agri-product-category">{product.category}</span>
                  <h2>{product.name}</h2>
                  <p>{product.detail}</p>
                  {product.description && <small>{product.description}</small>}
                  <div className="agri-product-footer">
                    <strong>{formatKsh(product.price)}</strong>
                    {whatsappUrl && whatsappDirectBypass ? (
                      <a href={whatsappUrl} target="_blank" rel="noreferrer">
                        <MessageCircle size={16} />
                        Contact Farmer on WhatsApp
                      </a>
                    ) : (
                      <span className="agri-contact-unavailable">
                        {whatsappDirectBypass ? "Farmer contact unavailable" : "Direct contact unavailable"}
                      </span>
                    )}
                  </div>
                </div>
              </article>
            );
          })
        ) : (
          <p className="agri-hub-empty">
            No listings are available in this category yet. Check back soon.
          </p>
        )}
      </section>
    </section>
  );
}

export default AgriFarmHub;
