import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, RefreshCw, ShieldAlert, Store } from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  fetchMarketplaceManagement,
  reviewMarketplaceVendor,
  updateMarketplaceVendor,
} from "../../services/api.js";
import "../../seller/Marketplace.css";

const SAVED_FILTER_KEY = "mm-admin-marketplace-vendor-filter";

function readFilter() {
  try {
    const saved = window.localStorage.getItem(SAVED_FILTER_KEY);
    return ["all", "pending", "active", "suspended", "audit"].includes(saved)
      ? saved
      : "all";
  } catch {
    return "all";
  }
}

function statusOf(vendor) {
  if (vendor.review_state === "UNDER_AUDIT") return "UNDER_AUDIT";
  if (vendor.status === "APPROVED") return "ACTIVE";
  return vendor.status;
}

function VendorManager() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(readFilter);
  const [reviewTarget, setReviewTarget] = useState(null);
  const [reviewAction, setReviewAction] = useState("");
  const [reviewReason, setReviewReason] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setData(await fetchMarketplaceManagement());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    try {
      window.localStorage.setItem(SAVED_FILTER_KEY, filter);
    } catch (storageError) {
      console.error("Could not persist marketplace vendor filter.", storageError);
    }
  }, [filter]);

  const filteredVendors = useMemo(() => (data?.vendors ?? []).filter((vendor) => {
    if (filter === "pending") return vendor.status === "PENDING";
    if (filter === "active") return statusOf(vendor) === "ACTIVE";
    if (filter === "suspended") return vendor.status === "SUSPENDED";
    if (filter === "audit") return statusOf(vendor) === "UNDER_AUDIT";
    return true;
  }), [data, filter]);

  const runReview = async () => {
    if (!reviewTarget || !reviewAction) return;
    setBusy(true);
    setError("");
    try {
      await reviewMarketplaceVendor(reviewTarget.id, reviewAction, reviewReason.trim());
      setReviewTarget(null);
      setReviewAction("");
      setReviewReason("");
      await refresh();
    } catch (reviewError) {
      setError(reviewError.message);
    } finally {
      setBusy(false);
    }
  };

  const openReview = (vendor, action) => {
    setReviewTarget(vendor);
    setReviewAction(action);
    setReviewReason("");
  };

  const changeStatus = async (vendor, status) => {
    setBusy(true);
    setError("");
    try {
      await updateMarketplaceVendor(vendor.id, status);
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <section className="vendor-manager-panel"><p>Loading seller governance…</p></section>;
  if (!data) return <section className="vendor-manager-panel"><p className="marketplace-error" role="alert">{error || "Seller data is unavailable."}</p><button className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Try again</button></section>;

  const pendingCount = data.vendors.filter((vendor) => vendor.status === "PENDING").length;
  const activeCount = data.vendors.filter((vendor) => statusOf(vendor) === "ACTIVE").length;
  return (
    <div className="vendor-manager">
      <header className="vendor-manager-heading">
        <div><span className="marketplace-eyebrow">MARKETPLACE OPERATIONS</span><h2>Vendor governance</h2><p>Verify applications and keep the seller roster healthy.</p></div>
        <button type="button" className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Refresh</button>
      </header>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      <section className="vendor-summary-grid">
        <article><span><Store size={17} /></span><small>Active sellers</small><strong>{activeCount}</strong></article>
        <article><span><ShieldAlert size={17} /></span><small>Pending applications</small><strong>{pendingCount}</strong></article>
        <article><span><Store size={17} /></span><small>All seller accounts</small><strong>{data.vendors.length}</strong></article>
      </section>
      <section className="vendor-manager-panel">
        <header className="vendor-governance-toolbar">
          <div><span className="marketplace-eyebrow">SELLER DIRECTORY</span><h2>Applications &amp; verified sellers <small>{filteredVendors.length}</small></h2></div>
          <label>Filter sellers<select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All sellers</option><option value="pending">Pending review</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="audit">Under audit</option>
          </select></label>
        </header>
        {filteredVendors.length ? <div className="vendor-list">
          {filteredVendors.map((vendor) => {
            const documents = vendor.submitted_documents ?? [];
            const vendorStatus = statusOf(vendor);
            return <article className="vendor-card" key={vendor.id}>
              <header>
                <div className="vendor-card-identity">
                  {vendor.logo_url ? <img src={vendor.logo_url} alt="" /> : <span><Store size={18} /></span>}
                  <div><strong>{vendor.store_name}</strong><small>Owner: {vendor.owner_name || "Not provided"}</small><small>{vendor.email} · {vendor.business_phone}</small><small>{vendor.payout_method}: {vendor.payout_account}</small></div>
                </div>
                <span className={`seller-status-badge ${vendorStatus.toLowerCase()}`}>{vendorStatus.replace("_", " ")}</span>
              </header>
              {vendor.review_note && <p className="vendor-review-note"><strong>Latest review:</strong> {vendor.review_note}</p>}
              <div className="vendor-card-meta">
                <span>Live products <strong>{vendor.live_product_count}</strong></span>
                <span>Store revenue <strong>{formatKsh(vendor.store_revenue)}</strong></span>
                <span>Rating average <strong>{Number(vendor.rating_average).toFixed(1)} / 5</strong></span>
                <span>Pending payout <strong>{formatKsh(vendor.pending_payout)}</strong></span>
              </div>
              {documents.length > 0 && <div className="vendor-document-previews"><strong>Submitted documents</strong><div>{documents.map((url, index) => <a href={url} target="_blank" rel="noreferrer" key={`${url}-${index}`}>{/\.(png|jpe?g|webp|gif)(?:[?#]|$)/i.test(url) ? <img src={url} alt={`Seller document ${index + 1}`} loading="lazy" /> : <span className="vendor-document-link-icon">DOC</span>}<span>Document {index + 1} <ExternalLink size={12} /></span></a>)}</div></div>}
              {vendor.banner_url && <a className="vendor-banner-preview" href={vendor.banner_url} target="_blank" rel="noreferrer"><img src={vendor.banner_url} alt={`${vendor.store_name} banner preview`} />Preview store banner <ExternalLink size={13} /></a>}
              <div className="vendor-card-actions">
                {vendor.status === "PENDING" && <>
                  <button type="button" className="marketplace-button primary" disabled={busy} onClick={() => openReview(vendor, "APPROVE")}><Check size={15} /> Approve seller</button>
                  <button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => openReview(vendor, "REJECT")}>Reject application</button>
                  <button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => openReview(vendor, "REQUEST_INFO")}>Request additional info</button>
                </>}
                {vendor.status === "APPROVED" && vendor.review_state !== "UNDER_AUDIT" && <>
                  <button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => openReview(vendor, "UNDER_AUDIT")}>Place under audit</button>
                  <button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => openReview(vendor, "SUSPEND")}>Suspend seller</button>
                </>}
                {(vendor.status === "SUSPENDED" || vendor.review_state === "UNDER_AUDIT") && <button type="button" className="marketplace-button primary" disabled={busy} onClick={() => openReview(vendor, "RESTORE")}>Restore seller</button>}
                {vendor.status !== "PENDING" && <a className="marketplace-button secondary" href={`/store/${encodeURIComponent(vendor.store_slug)}`} target="_blank" rel="noreferrer">View public store</a>}
              </div>
            </article>;
          })}
        </div> : <p className="marketplace-empty">No sellers match this filter.</p>}
      </section>
      {reviewTarget && <div className="marketplace-modal-backdrop" onMouseDown={() => setReviewTarget(null)}>
        <section className="marketplace-modal vendor-review-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-review-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">SELLER REVIEW</span><h2 id="vendor-review-title">{reviewAction === "REQUEST_INFO" ? "Request additional information" : reviewAction === "REJECT" ? "Reject seller application" : reviewAction === "UNDER_AUDIT" ? "Place seller under audit" : reviewAction === "SUSPEND" ? "Suspend seller" : reviewAction === "RESTORE" ? "Restore seller access" : "Approve seller"}</h2></div></header>
          <p>Application from <strong>{reviewTarget.store_name}</strong></p>
          <label className="marketplace-review-reason">{["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction) ? "Reason / information requested" : "Internal review note (optional)"}<textarea autoFocus required={["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction)} minLength={["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction) ? 3 : undefined} rows="4" maxLength="1000" value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} /></label>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" onClick={() => setReviewTarget(null)}>Cancel</button><button type="button" className="marketplace-button primary" disabled={busy} onClick={runReview}>{busy ? "Saving…" : "Confirm action"}</button></footer>
        </section>
      </div>}
    </div>
  );
}

export default VendorManager;
