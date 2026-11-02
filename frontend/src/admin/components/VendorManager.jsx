import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, Mail, RefreshCw, ShieldAlert, Store } from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  fetchMarketplaceManagement,
  createMarketplaceVendorWarning,
  fetchMarketplaceVendorWarnings,
  reviewMarketplaceVendor,
  updateMarketplaceVendor,
  updateMarketplaceVendorMaintenance,
  updateSellerPortalMaintenance,
} from "../../services/api.js";
import "../../seller/Marketplace.css";

const SAVED_FILTER_KEY = "mm-admin-marketplace-vendor-filter";

function readFilter() {
  try {
    const saved = window.localStorage.getItem(SAVED_FILTER_KEY);
    return ["all", "pending", "active", "suspended", "audit", "maintenance"].includes(saved)
      ? saved
      : "all";
  } catch {
    return "all";
  }
}

function statusOf(vendor) {
  if (vendor.maintenance_mode) return "MAINTENANCE";
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
  const [maintenanceTarget, setMaintenanceTarget] = useState(null);
  const [maintenanceReason, setMaintenanceReason] = useState("");
  const [portalMaintenanceDialog, setPortalMaintenanceDialog] = useState(false);
  const [portalMaintenanceReason, setPortalMaintenanceReason] = useState("");
  const [warningTarget, setWarningTarget] = useState(null);
  const [warningSummary, setWarningSummary] = useState("");
  const [warningReference, setWarningReference] = useState("");
  const [warningHistory, setWarningHistory] = useState([]);
  const [warningBusy, setWarningBusy] = useState(false);
  const [warningNotice, setWarningNotice] = useState("");

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
    if (filter === "maintenance") return Boolean(vendor.maintenance_mode);
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

  const changeMaintenance = async () => {
    if (!maintenanceTarget) return;
    const enabled = !maintenanceTarget.maintenance_mode;
    if (enabled && maintenanceReason.trim().length < 3) {
      setError("Enter a reason of at least 3 characters before enabling maintenance.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await updateMarketplaceVendorMaintenance(maintenanceTarget.id, {
        enabled,
        reason: enabled ? maintenanceReason.trim() : "",
      });
      setMaintenanceTarget(null);
      setMaintenanceReason("");
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  };

  const openMaintenance = (vendor) => {
    setMaintenanceTarget(vendor);
    setMaintenanceReason("");
    setError("");
  };

  const changePortalMaintenance = async () => {
    const enabled = !data.seller_portal_maintenance_enabled;
    if (enabled && portalMaintenanceReason.trim().length < 3) {
      setError("Enter a reason of at least 3 characters before enabling portal maintenance.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await updateSellerPortalMaintenance({
        enabled,
        reason: enabled ? portalMaintenanceReason.trim() : "",
      });
      setPortalMaintenanceDialog(false);
      setPortalMaintenanceReason("");
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  };

  const openReview = (vendor, action) => {
    setReviewTarget(vendor);
    setReviewAction(action);
    setReviewReason("");
  };

  const openWarning = async (vendor) => {
    setWarningTarget(vendor);
    setWarningSummary("");
    setWarningReference("");
    setWarningNotice("");
    setError("");
    setWarningBusy(true);
    try {
      setWarningHistory(await fetchMarketplaceVendorWarnings(vendor.id));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setWarningBusy(false);
    }
  };

  const sendWarning = async () => {
    if (!warningTarget || !warningSummary.trim()) return;
    setWarningBusy(true);
    setError("");
    setWarningNotice("");
    try {
      const warning = await createMarketplaceVendorWarning(warningTarget.id, {
        complaint_summary: warningSummary.trim(),
        complaint_reference: warningReference.trim(),
      });
      setWarningHistory((current) => [warning, ...current]);
      setWarningNotice(
        warning.delivery_status === "SENT"
          ? `Warning email sent to ${warningTarget.email}.`
          : warning.delivery_status === "NOT_CONFIGURED"
            ? "Warning recorded, but email was not sent: configure RESEND_API_KEY and RESEND_FROM_EMAIL."
            : "Warning recorded, but email delivery failed. Check Resend settings and backend mail logs.",
      );
      await refresh();
    } catch (warningError) {
      setError(warningError.message);
    } finally {
      setWarningBusy(false);
    }
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
      <section className="vendor-manager-panel">
        <header className="vendor-governance-toolbar">
          <div>
            <span className="marketplace-eyebrow">GLOBAL ACCESS CONTROL</span>
            <h2>Seller Portal maintenance</h2>
            <p>{data.seller_portal_maintenance_enabled
              ? "All sellers are blocked from Seller Studio."
              : "Seller Studio is available to sellers."}</p>
            {data.seller_portal_maintenance_enabled && data.seller_portal_maintenance_reason && (
              <p><strong>Reason:</strong> {data.seller_portal_maintenance_reason}</p>
            )}
          </div>
          <button
            type="button"
            className={`marketplace-button ${data.seller_portal_maintenance_enabled ? "primary" : "secondary"}`}
            disabled={busy}
            onClick={() => {
              setPortalMaintenanceReason("");
              setPortalMaintenanceDialog(true);
            }}
          >
            {data.seller_portal_maintenance_enabled ? "Restore seller access" : "Put Seller Portal under maintenance"}
          </button>
        </header>
      </section>
      <section className="vendor-summary-grid">
        <article><span><Store size={17} /></span><small>Active sellers</small><strong>{activeCount}</strong></article>
        <article><span><ShieldAlert size={17} /></span><small>Pending applications</small><strong>{pendingCount}</strong></article>
        <article><span><Store size={17} /></span><small>All seller accounts</small><strong>{data.vendors.length}</strong></article>
      </section>
      <section className="vendor-manager-panel">
        <header className="vendor-governance-toolbar">
          <div><span className="marketplace-eyebrow">SELLER DIRECTORY</span><h2>Applications &amp; verified sellers <small>{filteredVendors.length}</small></h2></div>
          <label>Filter sellers<select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All sellers</option><option value="pending">Pending review</option><option value="active">Active</option><option value="maintenance">Under maintenance</option><option value="suspended">Suspended</option><option value="audit">Under audit</option>
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
              {vendor.maintenance_mode && <p className="vendor-review-note"><strong>Maintenance reason:</strong> {vendor.maintenance_reason || "No reason recorded."}</p>}
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
                {vendor.status === "APPROVED" && <button type="button" className={`marketplace-button ${vendor.maintenance_mode ? "primary" : "secondary"}`} disabled={busy} onClick={() => openMaintenance(vendor)}>{vendor.maintenance_mode ? "End maintenance" : "Place under maintenance"}</button>}
                {(vendor.status === "SUSPENDED" || vendor.review_state === "UNDER_AUDIT") && <button type="button" className="marketplace-button primary" disabled={busy} onClick={() => openReview(vendor, "RESTORE")}>Restore seller</button>}
                {vendor.status !== "PENDING" && <a className="marketplace-button secondary" href={`/store/${encodeURIComponent(vendor.store_slug)}`} target="_blank" rel="noreferrer">View public store</a>}
                <button type="button" className="marketplace-button secondary" disabled={busy || warningBusy} onClick={() => openWarning(vendor)}><Mail size={15} /> Send complaint warning</button>
              </div>
            </article>;
          })}
        </div> : <p className="marketplace-empty">No sellers match this filter.</p>}
      </section>
      {portalMaintenanceDialog && <div className="marketplace-modal-backdrop" onMouseDown={() => !busy && setPortalMaintenanceDialog(false)}>
        <section className="marketplace-modal vendor-review-modal" role="dialog" aria-modal="true" aria-labelledby="seller-portal-maintenance-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">GLOBAL SELLER ACCESS</span><h2 id="seller-portal-maintenance-title">{data.seller_portal_maintenance_enabled ? "Restore Seller Portal access" : "Put all sellers under maintenance"}</h2></div></header>
          {data.seller_portal_maintenance_enabled
            ? <p>This will allow all sellers to sign in and use Seller Studio again.</p>
            : <><p>This blocks every seller from signing in, registering, and using Seller Studio APIs. The Super Admin dashboard remains available.</p>
              <label className="marketplace-review-reason">Reason for maintenance<textarea autoFocus required minLength="3" rows="4" maxLength="1000" value={portalMaintenanceReason} onChange={(event) => setPortalMaintenanceReason(event.target.value)} placeholder="For example: scheduled platform maintenance." /></label></>}
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => setPortalMaintenanceDialog(false)}>Cancel</button><button type="button" className="marketplace-button primary" disabled={busy || (!data.seller_portal_maintenance_enabled && portalMaintenanceReason.trim().length < 3)} onClick={changePortalMaintenance}>{busy ? "Saving…" : data.seller_portal_maintenance_enabled ? "Restore seller access" : "Block all sellers"}</button></footer>
        </section>
      </div>}
      {maintenanceTarget && <div className="marketplace-modal-backdrop" onMouseDown={() => !busy && setMaintenanceTarget(null)}>
        <section className="marketplace-modal vendor-review-modal" role="dialog" aria-modal="true" aria-labelledby="seller-maintenance-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">SELLER OPERATIONS</span><h2 id="seller-maintenance-title">{maintenanceTarget.maintenance_mode ? "End seller maintenance" : "Place seller under maintenance"}</h2></div></header>
          <p>Store: <strong>{maintenanceTarget.store_name}</strong></p>
          {maintenanceTarget.maintenance_mode
            ? <p>This will restore the public storefront and allow the seller to manage their store again.</p>
            : <><p>The seller’s public store and products will be hidden, and store-management actions will be paused. Existing account and order records remain unchanged.</p>
              <label className="marketplace-review-reason">Reason for maintenance<textarea autoFocus required minLength="3" rows="4" maxLength="1000" value={maintenanceReason} onChange={(event) => setMaintenanceReason(event.target.value)} placeholder="For example: temporary compliance review or store data updates." /></label></>}
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" disabled={busy} onClick={() => setMaintenanceTarget(null)}>Cancel</button><button type="button" className="marketplace-button primary" disabled={busy || (!maintenanceTarget.maintenance_mode && maintenanceReason.trim().length < 3)} onClick={changeMaintenance}>{busy ? "Saving…" : maintenanceTarget.maintenance_mode ? "End maintenance" : "Confirm maintenance"}</button></footer>
        </section>
      </div>}
      {reviewTarget && <div className="marketplace-modal-backdrop" onMouseDown={() => setReviewTarget(null)}>
        <section className="marketplace-modal vendor-review-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-review-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">SELLER REVIEW</span><h2 id="vendor-review-title">{reviewAction === "REQUEST_INFO" ? "Request additional information" : reviewAction === "REJECT" ? "Reject seller application" : reviewAction === "UNDER_AUDIT" ? "Place seller under audit" : reviewAction === "SUSPEND" ? "Suspend seller" : reviewAction === "RESTORE" ? "Restore seller access" : "Approve seller"}</h2></div></header>
          <p>Application from <strong>{reviewTarget.store_name}</strong></p>
          <label className="marketplace-review-reason">{["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction) ? "Reason / information requested" : "Internal review note (optional)"}<textarea autoFocus required={["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction)} minLength={["REJECT", "REQUEST_INFO", "UNDER_AUDIT", "SUSPEND"].includes(reviewAction) ? 3 : undefined} rows="4" maxLength="1000" value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} /></label>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" onClick={() => setReviewTarget(null)}>Cancel</button><button type="button" className="marketplace-button primary" disabled={busy} onClick={runReview}>{busy ? "Saving…" : "Confirm action"}</button></footer>
        </section>
      </div>}
      {warningTarget && <div className="marketplace-modal-backdrop" onMouseDown={() => !warningBusy && setWarningTarget(null)}>
        <section className="marketplace-modal vendor-review-modal" role="dialog" aria-modal="true" aria-labelledby="seller-warning-title" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">CUSTOMER COMPLAINT</span><h2 id="seller-warning-title">Send seller warning</h2></div></header>
          <p>Seller: <strong>{warningTarget.store_name}</strong> · {warningTarget.email}</p>
          <p className="vendor-warning-neutral">This sends a factual request for the seller’s response; it does not declare the complaint proven.</p>
          <label className="marketplace-review-reason">Complaint summary<textarea autoFocus required minLength="10" rows="4" maxLength="2000" value={warningSummary} onChange={(event) => setWarningSummary(event.target.value)} placeholder="Summarize the customer’s complaint and any relevant order facts." /></label>
          <label className="marketplace-review-reason">Order or support reference (optional)<input maxLength="100" value={warningReference} onChange={(event) => setWarningReference(event.target.value)} placeholder="Order ID or support ticket reference" /></label>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          {warningNotice && <p className="marketplace-notice" role="status">{warningNotice}</p>}
          <div className="vendor-warning-history">
            <strong>Recent warnings</strong>
            {warningBusy && !warningHistory.length ? <p>Loading warning history…</p> : warningHistory.length ? warningHistory.slice(0, 5).map((warning) => (
              <article key={warning.id}>
                <span className={`vendor-warning-delivery ${warning.delivery_status.toLowerCase()}`}>{warning.delivery_status.replace("_", " ")}</span>
                <small>{new Date(warning.created_at).toLocaleString()}</small>
                <p>{warning.complaint_summary}</p>
              </article>
            )) : <p>No warnings recorded for this seller.</p>}
          </div>
          <footer><button type="button" className="marketplace-button secondary" disabled={warningBusy} onClick={() => setWarningTarget(null)}>Close</button><button type="button" className="marketplace-button primary" disabled={warningBusy || warningSummary.trim().length < 10} onClick={sendWarning}>{warningBusy ? "Sending…" : "Record & send warning"}</button></footer>
        </section>
      </div>}
    </div>
  );
}

export default VendorManager;
