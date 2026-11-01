import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MessageCircle, Phone, ShieldCheck, Star, Store } from "lucide-react";
import { formatKsh } from "../data/currency.js";
import { fetchPublicStore } from "../services/api.js";
import { useFeatures } from "../context/FeatureContext.jsx";
import "../seller/Marketplace.css";

function StorePage() {
  const { verifiedSellerBadge, whatsappDirectBypass } = useFeatures();
  const { sellerSlug } = useParams();
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setResult(null);
    setError("");
    fetchPublicStore(sellerSlug)
      .then((storeResult) => {
        if (active) setResult(storeResult);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      });
    return () => { active = false; };
  }, [sellerSlug]);

  if (error) {
    return <main className="store-page"><Link to="/" className="store-back-link">← Maison Muse</Link><section className="store-state" role="alert"><Store size={25} /><h1>We couldn’t find this store.</h1><p>{error}</p><Link to="/shop">Explore the marketplace</Link></section></main>;
  }
  if (!result) return <main className="store-page"><p className="store-loading">Loading store…</p></main>;

  const { store, products } = result;
  const supportPhone = store.whatsapp_phone || store.business_phone;
  const whatsappNumber = supportPhone.replace(/\D/g, "").replace(/^0/, "254");
  const isAgricultureSeller =
    store.business_type === "Agriculture & Livestock Farming";
  return (
    <main className="store-page">
      <header className="store-nav"><Link to="/" className="marketplace-brand">maison <span>muse.</span></Link><Link to="/shop">Explore marketplace</Link></header>
      <section className="store-hero">
        {store.banner_url && <img className="store-banner-image" src={store.banner_url} alt="" />}
        <div className="store-hero-shade" />
        <div className="store-identity">
          {store.logo_url ? <img src={store.logo_url} alt={`${store.store_name} logo`} /> : <span className="store-logo-placeholder"><Store size={25} /></span>}
          <div><span className="marketplace-eyebrow">{store.business_category || "MAISON MUSE SELLER"}</span><h1>{store.store_name}</h1><p><Star size={15} fill="currentColor" /> {Number(store.rating).toFixed(1)} seller rating <span>·</span> {products.length} {products.length === 1 ? "item" : "items"}</p></div>
        </div>
      </section>
      <section className="store-support-card" aria-label="Merchant contact and support">
        <div className="store-support-heading">
          {verifiedSellerBadge && <ShieldCheck size={23} aria-hidden="true" />}
          <div><span className="marketplace-eyebrow">{verifiedSellerBadge ? "VERIFIED MAISON MUSE BOUTIQUE" : "MAISON MUSE BOUTIQUE"}</span><h2>Merchant Contact &amp; Support</h2></div>
        </div>
        <p><Star size={15} fill="currentColor" /> {Number(store.rating).toFixed(1)} seller rating <span>·</span> Typically replies within 15 minutes</p>
        <div className="store-support-actions">
          {(!isAgricultureSeller || whatsappDirectBypass) && (
            <a href={`tel:${store.business_phone.replace(/[^\d+]/g, "")}`}><Phone size={15} /> {store.business_phone}</a>
          )}
          {(!isAgricultureSeller || whatsappDirectBypass) && (
            <a className="store-whatsapp-button" href={`https://wa.me/${whatsappNumber}`} target="_blank" rel="noreferrer"><MessageCircle size={15} /> Chat on WhatsApp</a>
          )}
        </div>
        {(store.instagram_url || store.tiktok_url) && (
          <div className="store-social-links">
            {store.instagram_url && <a href={store.instagram_url} target="_blank" rel="noreferrer">Instagram</a>}
            {store.tiktok_url && <a href={store.tiktok_url} target="_blank" rel="noreferrer">TikTok</a>}
          </div>
        )}
        {store.operating_hours && <small>Operating hours: {store.operating_hours}</small>}
      </section>
      {store.holiday_mode && <p className="store-holiday-notice">This boutique is on holiday pause. Its catalog remains visible, but new orders are temporarily paused.</p>}
      <section className="store-catalog">
        <div className="store-catalog-heading"><span className="marketplace-eyebrow">THE STORE EDIT</span><h2>Shop {store.store_name}</h2><p>{store.store_bio || "Thoughtful finds, selected by this Maison Muse seller."}</p></div>
        {products.length ? <div className="store-product-grid">{products.map((product) => <article className="store-product-card" key={product.id}>
          <div><img src={product.image} alt={product.name} loading="lazy" />{product.stock <= 0 && <span className="store-sold-out">Sold out</span>}</div>
          <span>{product.category}</span><h3>{product.name}</h3><p>{product.detail}</p><strong>{formatKsh(product.price)}</strong>
          <small>Sold &amp; fulfilled by {store.store_name} {verifiedSellerBadge && <ShieldCheck size={13} aria-label="Verified seller" />}</small>
        </article>)}</div> : <p className="marketplace-empty">This store is preparing its first collection.</p>}
      </section>
      <footer className="store-footer"><Link to="/">Maison Muse</Link><span>Beauty, made personal.</span></footer>
    </main>
  );
}

export default StorePage;
