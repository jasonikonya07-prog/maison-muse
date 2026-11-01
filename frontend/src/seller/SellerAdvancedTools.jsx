import { useEffect, useMemo, useState } from "react";
import {
  boostSellerProduct,
  createSellerPromotion,
  enrollSellerCampaign,
  fetchSellerAds,
  fetchSellerCampaigns,
  fetchSellerHealth,
  fetchSellerPromotions,
  fetchSellerProductCsvTemplate,
  fetchSellerReturns,
  updateSellerReturn,
  uploadSellerProductsCsv,
} from "../services/api.js";
import { formatKsh } from "../data/currency.js";

const dateInputValue = (date) => {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return localDate.toISOString().slice(0, 10);
};

function SellerHealthPanel({ demoMode }) {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    fetchSellerHealth()
      .then((result) => {
        if (active) setHealth(result);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      });
    return () => { active = false; };
  }, [demoMode]);

  return (
    <section className="seller-panel">
      <header>
        <div><span className="marketplace-eyebrow">SELLER HEALTH</span><h2>Performance scorecard</h2></div>
      </header>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      <div className="seller-advanced-grid">
        {[
          ["Cancellation rate", `${health?.cancellation_rate ?? "—"}%`, "Target below 1%"],
          ["On-time dispatch", `${health?.on_time_dispatch_rate ?? "—"}%`, "Orders dispatched within 24 hours"],
          ["Average rating", health ? `${health.average_rating.toFixed(1)} ★` : "—", "Customer product reviews"],
          ["Return / dispute rate", `${health?.return_dispute_rate ?? "—"}%`, "Keep resolutions timely"],
        ].map(([label, value, detail]) => (
          <article className="seller-advanced-card" key={label}>
            <span>{label}</span><strong>{value}</strong><small>{detail}</small>
          </article>
        ))}
      </div>
      <div className="seller-badge-list" aria-label="Seller achievements">
        {(health?.badges ?? []).length ? health.badges.map((badge) => (
          <span className="seller-achievement-badge" key={badge}>{badge}</span>
        )) : <small>Achievement badges appear as you build your order and service history.</small>}
      </div>
    </section>
  );
}

function PromotionsManager({ products, demoMode, onNotice }) {
  const [promotions, setPromotions] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState("");
  const [campaignProductIds, setCampaignProductIds] = useState([]);
  const [form, setForm] = useState({
    promotion_type: "flash_sale",
    name: "",
    product_ids: [],
    discount_percent: "15",
    code: "",
    usage_limit: "100",
    expires_at: dateInputValue(new Date(Date.now() + 7 * 86400000)),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [activePromotions, activeCampaigns] = await Promise.all([
      fetchSellerPromotions(),
      fetchSellerCampaigns(),
    ]);
    setPromotions(activePromotions);
    setCampaigns(activeCampaigns);
  };
  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    Promise.all([fetchSellerPromotions(), fetchSellerCampaigns()])
      .then(([activePromotions, activeCampaigns]) => {
        if (!active) return;
        setPromotions(activePromotions);
        setCampaigns(activeCampaigns);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      });
    return () => { active = false; };
  }, [demoMode]);

  const toggleProduct = (productId) => {
    setForm((current) => ({
      ...current,
      product_ids: current.product_ids.includes(productId)
        ? current.product_ids.filter((id) => id !== productId)
        : [...current.product_ids, productId],
    }));
  };
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await createSellerPromotion({
        ...form,
        discount_percent: Number(form.discount_percent),
        usage_limit: Number(form.usage_limit),
        code: form.promotion_type === "coupon" ? form.code.trim().toUpperCase() : "",
        expires_at: new Date(`${form.expires_at}T23:59:59`).toISOString(),
      });
      await load();
      onNotice("Promotion saved. Price discounts are now reflected on the selected listings.");
      setForm((current) => ({ ...current, name: "", code: "", product_ids: [] }));
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  };
  const enroll = async () => {
    setBusy(true);
    setError("");
    try {
      await enrollSellerCampaign(campaignId, campaignProductIds);
      await load();
      onNotice("Selected products were enrolled in the platform campaign.");
    } catch (enrollError) {
      setError(enrollError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="seller-tab-content">
      <section className="seller-panel">
        <header><div><span className="marketplace-eyebrow">CAMPAIGNS</span><h2>Flash sales &amp; promotional discounts</h2></div></header>
        {campaigns.length ? (
          <div className="seller-advanced-grid">
            {campaigns.map((campaign) => (
              <article className="seller-advanced-card" key={campaign.id}>
                <span>Platform campaign</span><strong>{campaign.title}</strong>
                <small>{campaign.discount_percent}% discount · ends {new Date(campaign.ends_at).toLocaleDateString()}</small>
                <small>{campaign.enrolled ? `${campaign.product_ids.length} enrolled products` : "Open to seller enrollment"}</small>
              </article>
            ))}
          </div>
        ) : <p className="marketplace-empty">No platform-wide campaigns are open right now. You can still create your own offer below.</p>}
        {campaigns.length > 0 && <div className="seller-advanced-form">
          <label>Open platform campaign<select value={campaignId} onChange={(event) => setCampaignId(event.target.value)}><option value="">Select a campaign</option>{campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.title}</option>)}</select></label>
          <label>Products for campaign<select multiple value={campaignProductIds} onChange={(event) => setCampaignProductIds(Array.from(event.target.selectedOptions, (option) => option.value))}>{products.filter((product) => product.status === "ACTIVE" && product.stock > 0).map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
          <button type="button" className="marketplace-button primary" disabled={demoMode || busy || !campaignId || !campaignProductIds.length} onClick={enroll}>{busy ? "Enrolling…" : "Enroll selected products"}</button>
        </div>}
        {error && <p className="marketplace-error" role="alert">{error}</p>}
      </section>
      <section className="seller-panel">
        <header><div><span className="marketplace-eyebrow">YOUR OFFERS</span><h2>Create a campaign or coupon</h2></div></header>
        <form className="seller-advanced-form" onSubmit={submit}>
          <label>Offer type<select value={form.promotion_type} onChange={(event) => setForm((current) => ({ ...current, promotion_type: event.target.value }))}>
            <option value="flash_sale">Flash sale</option><option value="price_discount">Product discount</option><option value="coupon">Coupon code</option>
          </select></label>
          <label>Campaign name<input required minLength="2" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="Weekend Beauty Deals" /></label>
          <label>Discount (%)<input type="number" min="1" max="90" value={form.discount_percent} onChange={(event) => setForm((current) => ({ ...current, discount_percent: event.target.value }))} /></label>
          {form.promotion_type === "coupon" && <>
            <label>Promo code<input required minLength="3" maxLength="32" value={form.code} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="LUXE20" /></label>
            <label>Usage limit<input type="number" min="0" value={form.usage_limit} onChange={(event) => setForm((current) => ({ ...current, usage_limit: event.target.value }))} /></label>
          </>}
          <label>Expires on<input type="date" required min={dateInputValue(new Date())} value={form.expires_at} onChange={(event) => setForm((current) => ({ ...current, expires_at: event.target.value }))} /></label>
          <fieldset className="seller-product-picker">
            <legend>Products included</legend>
            {products.length ? products.map((product) => (
              <label key={product.id}><input type="checkbox" checked={form.product_ids.includes(product.id)} onChange={() => toggleProduct(product.id)} /> {product.name}</label>
            )) : <small>Add products to your catalog before creating an offer.</small>}
          </fieldset>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <button type="submit" className="marketplace-button primary" disabled={demoMode || busy || !form.product_ids.length}>{busy ? "Saving…" : "Save promotion"}</button>
        </form>
        {promotions.length > 0 && <div className="seller-advanced-list">
          {promotions.map((promotion) => <article key={promotion.id}>
            <div><strong>{promotion.name}</strong><small>{promotion.product_names.join(", ")}</small></div>
            <span>{promotion.code || `${promotion.discount_percent}% off`}</span><small>{promotion.status} · until {new Date(promotion.expires_at).toLocaleDateString()}</small>
          </article>)}
        </div>}
      </section>
    </div>
  );
}

function ReturnsManager({ demoMode, onNotice }) {
  const [returns, setReturns] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    fetchSellerReturns()
      .then((items) => { if (active) setReturns(items); })
      .catch((loadError) => { if (active) setError(loadError.message); });
    return () => { active = false; };
  }, [demoMode]);
  const decide = async (item, action) => {
    setBusyId(item.id);
    setError("");
    try {
      const updated = await updateSellerReturn(item.id, {
        action,
        resolution_note: action === "escalated" ? "Submitted to Maison Muse for arbitration." : "",
      });
      setReturns((current) => current.map((entry) => entry.id === item.id ? { ...entry, status: updated.status } : entry));
      onNotice(`Return ${item.order_number} updated: ${updated.status.replaceAll("_", " ").toLowerCase()}.`);
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusyId(null);
    }
  };
  return (
    <div className="seller-tab-content">
      <section className="seller-panel">
        <header><div><span className="marketplace-eyebrow">AFTER-SALES SUPPORT</span><h2>Returns &amp; dispute arbitration</h2></div></header>
        <p>These actions record the resolution decision only; refunds and replacements still require your normal fulfilment or payment workflow.</p>
        {error && <p className="marketplace-error" role="alert">{error}</p>}
        {returns.length ? <div className="seller-advanced-list">
          {returns.map((item) => <article className="seller-return-card" key={item.id}>
            <div><strong>Order {item.order_number}</strong><small>{item.customer.name} · {item.customer.phone}</small><small>{item.reason}</small><small>{item.items.map((orderItem) => `${orderItem.product_name} × ${orderItem.quantity}`).join(", ")}</small></div>
            <span className={`seller-status-badge ${item.status.toLowerCase()}`}>{item.status.replaceAll("_", " ")}</span>
            {item.status === "OPEN" && <div className="seller-return-actions">
              <button type="button" className="marketplace-button secondary" disabled={busyId === item.id || demoMode} onClick={() => decide(item, "replacement_offered")}>Offer replacement</button>
              <button type="button" className="marketplace-button secondary" disabled={busyId === item.id || demoMode} onClick={() => decide(item, "refund_approved")}>Record refund approval</button>
              <button type="button" className="marketplace-button primary" disabled={busyId === item.id || demoMode} onClick={() => decide(item, "escalated")}>Send to arbitration</button>
            </div>}
          </article>)}
        </div> : <p className="marketplace-empty">No return or dispute requests have been filed for your orders.</p>}
      </section>
    </div>
  );
}

function SponsoredAds({ products, demoMode, onNotice }) {
  const [ads, setAds] = useState({ items: [], available_balance: 0 });
  const [productId, setProductId] = useState("");
  const [amount, setAmount] = useState("500");
  const [duration, setDuration] = useState("3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeProducts = useMemo(() => products.filter((product) => product.status === "ACTIVE" && product.stock > 0), [products]);

  const load = async () => setAds(await fetchSellerAds());
  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    fetchSellerAds()
      .then((result) => { if (active) setAds(result); })
      .catch((loadError) => { if (active) setError(loadError.message); });
    return () => { active = false; };
  }, [demoMode]);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await boostSellerProduct({
        product_id: productId,
        amount: Number(amount),
        duration_days: Number(duration),
      });
      await load();
      onNotice(`${result.reference} · simulated listing boost is live until ${new Date(result.boosted_until).toLocaleDateString()}.`);
    } catch (boostError) {
      setError(boostError.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="seller-tab-content">
      <section className="seller-panel">
        <header><div><span className="marketplace-eyebrow">SPONSORED DISCOVERY</span><h2>Boost products in category search</h2></div></header>
        <p>Ad spend is simulated and deducted from your available seller escrow. Sponsored listings are labeled for buyers.</p>
        <p className="seller-escrow-amount">Available seller balance: <strong>{formatKsh(ads.available_balance)}</strong></p>
        <form className="seller-advanced-form" onSubmit={submit}>
          <label>Product<select required value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Select a product</option>{activeProducts.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
          <label>Spend (KSh)<input type="number" min="500" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
          <label>Duration<select value={duration} onChange={(event) => setDuration(event.target.value)}><option value="3">3 days</option><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <button className="marketplace-button primary" type="submit" disabled={demoMode || busy || !productId || Number(amount) < 500}>{busy ? "Starting…" : "Start simulated sponsored boost"}</button>
        </form>
        {ads.items.length > 0 && <div className="seller-advanced-list">{ads.items.map((ad) => <article key={ad.id}>
          <div><strong>{ad.product_name}</strong><small>{ad.reference} · {ad.duration_days} day boost</small></div>
          <span>{formatKsh(ad.amount)}</span><small>{ad.status} · through {new Date(ad.boosted_until).toLocaleDateString()}</small>
        </article>)}</div>}
      </section>
    </div>
  );
}

function downloadTemplate(template) {
  const csvEscape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [
    template.headers.map(csvEscape).join(","),
    template.example.map(csvEscape).join(","),
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "maison-muse-product-template.csv";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function BulkProductManager({ demoMode, onImported, onNotice }) {
  const [template, setTemplate] = useState(null);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    fetchSellerProductCsvTemplate()
      .then((value) => { if (active) setTemplate(value); })
      .catch((loadError) => { if (active) setError(loadError.message); });
    return () => { active = false; };
  }, [demoMode]);

  const upload = async (event) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const summary = await uploadSellerProductsCsv(file);
      setResult(summary);
      if (summary.created) {
        await onImported();
        onNotice(`${summary.created} product${summary.created === 1 ? "" : "s"} imported.`);
      }
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="seller-panel seller-bulk-import">
      <header><div><span className="marketplace-eyebrow">BULK CATALOG TOOLS</span><h2>CSV &amp; Excel import</h2></div>
        <button type="button" className="marketplace-button secondary" disabled={!template} onClick={() => downloadTemplate(template)}>Download CSV template</button>
      </header>
      <p>Upload up to 500 listings in a UTF-8 CSV or .xlsx workbook (maximum 5 MB). Separate image URLs with <code>|</code> and variant groups with semicolons. New imports await QC review.</p>
      <form className="seller-advanced-form" onSubmit={upload}>
        <label className="seller-file-input">Choose catalog file<input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || busy || !file}>{busy ? "Importing…" : "Import products"}</button>
      </form>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      {result && <div className="seller-import-result" role="status"><strong>{result.created} created · {result.failed} failed</strong>
        {result.errors?.length > 0 && <ul>{result.errors.map((item) => <li key={`${item.row}-${item.message}`}>Row {item.row}: {item.message}</li>)}</ul>}
      </div>}
    </section>
  );
}

export default function SellerAdvancedTools({ tab, products, demoMode, onNotice, onProductsImported }) {
  if (tab === "health") return <SellerHealthPanel demoMode={demoMode} />;
  if (tab === "promotions") return <PromotionsManager products={products} demoMode={demoMode} onNotice={onNotice} />;
  if (tab === "sponsored") return <SponsoredAds products={products} demoMode={demoMode} onNotice={onNotice} />;
  if (tab === "returns") return <ReturnsManager demoMode={demoMode} onNotice={onNotice} />;
  if (tab === "bulk") {
    return <BulkProductManager demoMode={demoMode} onImported={onProductsImported} onNotice={onNotice} />;
  }
  return null;
}
