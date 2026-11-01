import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight,
  CircleDollarSign,
  RefreshCw,
  Store,
  Wallet,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import { fetchMarketplaceAnalytics } from "../../services/api.js";
import "../../seller/Marketplace.css";

function AnalyticsOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setData(await fetchMarketplaceAnalytics());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  if (loading) return <section className="vendor-manager-panel"><p>Loading marketplace analytics…</p></section>;
  if (!data) return <section className="vendor-manager-panel"><p className="marketplace-error" role="alert">{error || "Marketplace analytics are unavailable."}</p><button className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Try again</button></section>;

  const metrics = [
    { label: "Gross merchandise value", value: formatKsh(data.gmv), icon: CircleDollarSign, detail: "Paid seller order volume" },
    { label: "Platform net revenue", value: formatKsh(data.platform_net_revenue), icon: ArrowUpRight, detail: "Commission retained" },
    { label: "Total vendor payouts", value: formatKsh(data.vendor_payouts), icon: Wallet, detail: "Completed dispatch ledger" },
    { label: "Active sellers", value: data.active_sellers, icon: Store, detail: "Approved and not under audit" },
  ];

  return (
    <div className="vendor-manager analytics-overview">
      <header className="vendor-manager-heading"><div><span className="marketplace-eyebrow">MARKETPLACE PERFORMANCE</span><h2>Marketplace analytics</h2><p>Financial and seller performance from recorded paid orders.</p></div><button type="button" className="marketplace-button secondary" onClick={refresh}><RefreshCw size={15} /> Refresh</button></header>
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      <section className="vendor-summary-grid analytics-metric-grid">{metrics.map(({ label, value, icon: Icon, detail }) => <article key={label}><span><Icon size={17} /></span><small>{label}</small><strong>{value}</strong><p>{detail}</p></article>)}</section>
      <section className="vendor-manager-panel">
        <header><div><span className="marketplace-eyebrow">SELLER PERFORMANCE</span><h2>Top-performing vendors <small>{data.top_vendors.length}</small></h2></div></header>
        {data.top_vendors.length ? <div className="analytics-vendor-table-wrap"><table className="analytics-vendor-table"><thead><tr><th>Rank</th><th>Seller</th><th>Rating</th><th>Paid orders</th><th>Store revenue</th></tr></thead><tbody>{data.top_vendors.map((vendor, index) => <tr key={vendor.id}><td><span className="analytics-rank">{String(index + 1).padStart(2, "0")}</span></td><td><strong>{vendor.store_name}</strong></td><td>{Number(vendor.rating).toFixed(1)} / 5</td><td>{vendor.orders}</td><td><strong>{formatKsh(vendor.revenue)}</strong></td></tr>)}</tbody></table></div> : <p className="marketplace-empty">Vendor revenue rankings will appear after the first paid marketplace order.</p>}
      </section>
      <p className="commission-policy-note">GMV, net revenue, and payout totals reflect paid vendor sub-orders. Completed payout values represent transfers recorded by an administrator, not provider-confirmed transfers unless a provider reference was entered.</p>
    </div>
  );
}

export default AnalyticsOverview;
