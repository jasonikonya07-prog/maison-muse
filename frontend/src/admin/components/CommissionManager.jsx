import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, CircleDollarSign, RefreshCw, Wallet } from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  createMarketplacePayout,
  fetchMarketplaceCommissions,
  fetchMarketplaceManagement,
  updateMarketplaceCommissions,
  updateMarketplacePayout,
} from "../../services/api.js";
import "../../seller/Marketplace.css";

const CATEGORIES = [
  "Perfumes & Fragrances",
  "Press-On Nails",
  "Skincare & Glow",
  "Lip & Makeup Essentials",
  "Hair & Accessories",
];

function CommissionManager() {
  const [settings, setSettings] = useState(null);
  const [marketplace, setMarketplace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [references, setReferences] = useState({});
  const [dispatch, setDispatch] = useState(null);
  const [transactionId, setTransactionId] = useState("");
  const [failureReason, setFailureReason] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [commissionData, managementData] = await Promise.all([
        fetchMarketplaceCommissions(),
        fetchMarketplaceManagement(),
      ]);
      const sellerCategoryRates = {};
      for (const rate of commissionData.seller_category_rates ?? []) {
        sellerCategoryRates[rate.seller_id] ??= {};
        sellerCategoryRates[rate.seller_id][rate.category] = rate.percentage;
      }
      setSettings({
        ...commissionData,
        seller_category_rates: sellerCategoryRates,
      });
      setMarketplace(managementData);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const saveSettings = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateMarketplaceCommissions({
        default_percentage: Number(settings.default_percentage),
        category_rates: Object.fromEntries(
          Object.entries(settings.category_rates).filter(([, value]) => value !== "" && value !== null),
        ),
        seller_rates: Object.fromEntries(
          Object.entries(settings.seller_rates).filter(([, value]) => value !== "" && value !== null),
        ),
        seller_category_rates: Object.fromEntries(
          Object.entries(settings.seller_category_rates)
            .map(([sellerId, rates]) => [
              sellerId,
              Object.fromEntries(
                Object.entries(rates).filter(([, value]) => value !== "" && value !== null),
              ),
            ])
            .filter(([, rates]) => Object.keys(rates).length > 0),
        ),
      });
      setNotice("Commission policy saved. New orders will use these rates.");
      await refresh();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const availableSellers = useMemo(
    () => (marketplace?.vendors ?? []).filter((vendor) => vendor.status === "APPROVED"),
    [marketplace],
  );

  const startDispatch = async (vendor) => {
    const subOrderIds = vendor.pending_sub_orders.map((order) => order.id);
    if (!subOrderIds.length) return;
    const reference = (references[vendor.id] ?? "").trim();
    if (!reference) {
      setError("Create a unique dispatch reference before starting the payout.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await createMarketplacePayout({
        seller_id: vendor.id,
        sub_order_ids: subOrderIds,
        reference,
      });
      setNotice(`Payout ${result.reference} is queued as PROCESSING. Complete the external transfer before entering its transaction ID.`);
      await refresh();
    } catch (dispatchError) {
      setError(dispatchError.message);
    } finally {
      setSaving(false);
    }
  };

  const saveDispatchStatus = async (event) => {
    event.preventDefault();
    if (!dispatch) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateMarketplacePayout(dispatch.id, {
        status: dispatch.status,
        transaction_id: transactionId.trim(),
        failure_reason: failureReason.trim(),
      });
      setNotice(`Payout ${dispatch.reference} updated to ${dispatch.status}.`);
      setDispatch(null);
      setTransactionId("");
      setFailureReason("");
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <section className="vendor-manager-panel"><p>Loading commission policy and payout ledger…</p></section>;
  if (!settings || !marketplace) return <section className="vendor-manager-panel"><p className="marketplace-error" role="alert">{error || "Financial settings are unavailable."}</p><button className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Try again</button></section>;

  const openPayouts = marketplace.payout_transactions.filter((payout) => payout.status === "PROCESSING");
  return (
    <div className="vendor-manager">
      <header className="vendor-manager-heading"><div><span className="marketplace-eyebrow">MARKETPLACE FINANCE</span><h2>Commissions &amp; payouts</h2><p>Configure future order commissions and reconcile eligible seller balances.</p></div><button type="button" className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Refresh</button></header>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      {notice && <p className="marketplace-notice" role="status">{notice}</p>}
      <section className="vendor-summary-grid">
        <article><span><CircleDollarSign size={17} /></span><small>Platform commissions earned</small><strong>{formatKsh(marketplace.total_commissions)}</strong></article>
        <article><span><Wallet size={17} /></span><small>Pending eligible payouts</small><strong>{formatKsh(marketplace.pending_payouts)}</strong></article>
        <article><span><Wallet size={17} /></span><small>Processing dispatches</small><strong>{openPayouts.length}</strong></article>
      </section>
      <form className="vendor-manager-panel commission-settings-form" onSubmit={saveSettings}>
        <header><div><span className="marketplace-eyebrow">RATE POLICY</span><h2>Global &amp; tiered commission</h2></div></header>
        <label className="commission-default-field">Default platform commission (%)
          <input type="number" min="0" max="100" step="0.1" required value={settings.default_percentage} onChange={(event) => setSettings((current) => ({ ...current, default_percentage: event.target.value }))} />
        </label>
        <h3>Category overrides</h3>
        <div className="commission-rate-grid">{CATEGORIES.map((category) => <label key={category}>{category} (%)
          <input type="number" min="0" max="100" step="0.1" placeholder={`Default: ${settings.default_percentage}%`} value={settings.category_rates[category] ?? ""} onChange={(event) => setSettings((current) => ({ ...current, category_rates: { ...current.category_rates, [category]: event.target.value } }))} />
        </label>)}</div>
        <h3>Seller-specific overrides</h3>
        {availableSellers.length ? <div className="commission-seller-list">{availableSellers.map((vendor) => <fieldset key={vendor.id}><legend>{vendor.store_name}</legend>
          <label>Default seller rate (%)<input type="number" min="0" max="100" step="0.1" placeholder={`Global: ${settings.default_percentage}%`} value={settings.seller_rates[vendor.id] ?? ""} onChange={(event) => setSettings((current) => ({ ...current, seller_rates: { ...current.seller_rates, [vendor.id]: event.target.value } }))} /></label>
          <div className="commission-rate-grid">{CATEGORIES.map((category) => <label key={category}>{category}
            <input type="number" min="0" max="100" step="0.1" placeholder="Use seller/global rate" value={settings.seller_category_rates[vendor.id]?.[category] ?? ""} onChange={(event) => setSettings((current) => ({ ...current, seller_category_rates: { ...current.seller_category_rates, [vendor.id]: { ...current.seller_category_rates[vendor.id], [category]: event.target.value } } }))} />
          </label>)}</div>
        </fieldset>)}</div> : <p className="marketplace-empty">Approved sellers will appear here for individual rate overrides.</p>}
        <p className="commission-policy-note">These settings apply to new orders only. Existing seller order commission amounts are not recalculated.</p>
        <button type="submit" className="marketplace-button primary" disabled={saving}><Check size={15} /> {saving ? "Saving…" : "Save commission policy"}</button>
      </form>
      <section className="vendor-manager-panel">
        <header><div><span className="marketplace-eyebrow">PAYOUT DISPATCH</span><h2>Pending eligible balances</h2></div></header>
        <p className="commission-policy-note">Starting a payout reserves the selected eligible orders as PROCESSING; it does not transmit funds. Complete the M-Pesa/bank transfer through your provider, then enter its transaction ID below.</p>
        <div className="vendor-list">{marketplace.vendors.filter((vendor) => vendor.pending_sub_orders.length).map((vendor) => <article className="vendor-card" key={vendor.id}>
          <header><div className="vendor-card-identity"><span><Wallet size={18} /></span><div><strong>{vendor.store_name}</strong><small>{vendor.payout_method} · {vendor.payout_account}</small></div></div><strong>{formatKsh(vendor.pending_payout)}</strong></header>
          <div className="commission-payout-orders">{vendor.pending_sub_orders.map((order) => <span key={order.id}>{order.order_number} · {formatKsh(order.amount)}</span>)}</div>
          <div className="commission-dispatch-controls"><input aria-label={`Payout dispatch reference for ${vendor.store_name}`} placeholder="Unique dispatch reference" value={references[vendor.id] ?? ""} onChange={(event) => setReferences((current) => ({ ...current, [vendor.id]: event.target.value }))} /><button type="button" className="marketplace-button primary" disabled={saving} onClick={() => startDispatch(vendor)}>Start manual dispatch</button></div>
        </article>)}</div>
        {!marketplace.vendors.some((vendor) => vendor.pending_sub_orders.length) && <p className="marketplace-empty">No paid, delivered seller orders are awaiting payout.</p>}
      </section>
      <section className="vendor-manager-panel">
        <header><div><span className="marketplace-eyebrow">PAYOUT LEDGER</span><h2>Dispatch history <small>{marketplace.payout_transactions.length}</small></h2></div></header>
        {marketplace.payout_transactions.length ? <div className="vendor-payout-ledger">{marketplace.payout_transactions.map((payout) => <article key={payout.id}>
          <div><strong>{payout.store_name} · {formatKsh(payout.amount)}</strong><small>Dispatch {payout.reference} · Transaction {payout.transaction_id || "not recorded"} · Commission retained {formatKsh(payout.commission_retained)}</small><small>{payout.payout_method} · {new Date(payout.created_at).toLocaleString()} · {payout.paid_by}</small>{payout.failure_reason && <small className="marketplace-error">{payout.failure_reason}</small>}</div>
          <span className={`seller-status-badge ${payout.status.toLowerCase()}`}>{payout.status}</span>
          {payout.status === "PROCESSING" && <button type="button" className="marketplace-button secondary" onClick={() => { setDispatch(payout); setTransactionId(payout.transaction_id ?? ""); setFailureReason(""); }}>Update status</button>}
        </article>)}</div> : <p className="marketplace-empty">Payout dispatches will appear here.</p>}
      </section>
      {dispatch && <div className="marketplace-modal-backdrop" onMouseDown={() => setDispatch(null)}>
        <form className="marketplace-modal" onSubmit={saveDispatchStatus} onMouseDown={(event) => event.stopPropagation()}>
          <header><div><span className="marketplace-eyebrow">MANUAL TRANSFER RECONCILIATION</span><h2>Update payout {dispatch.reference}</h2></div></header>
          <label className="marketplace-review-reason">Dispatch status<select required value={dispatch.status} onChange={(event) => setDispatch((current) => ({ ...current, status: event.target.value }))}><option value="PROCESSING">PROCESSING</option><option value="COMPLETED">COMPLETED</option><option value="FAILED">FAILED</option></select></label>
          {dispatch.status === "COMPLETED" && <label className="marketplace-review-reason">M-Pesa / bank transaction ID<input required value={transactionId} onChange={(event) => setTransactionId(event.target.value)} /></label>}
          {dispatch.status === "FAILED" && <label className="marketplace-review-reason">Failure reason<textarea required minLength="3" rows="3" value={failureReason} onChange={(event) => setFailureReason(event.target.value)} /></label>}
          <p className="commission-policy-note">Only mark COMPLETED after confirming the transfer externally. Failed dispatches release their reserved seller orders for a future retry.</p>
          <footer><button type="button" className="marketplace-button secondary" onClick={() => setDispatch(null)}>Cancel</button><button type="submit" className="marketplace-button primary" disabled={saving}>{saving ? "Saving…" : "Save payout status"}</button></footer>
        </form>
      </div>}
    </div>
  );
}

export default CommissionManager;
