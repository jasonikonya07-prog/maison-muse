import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  ClipboardList,
  PackageCheck,
  RefreshCw,
  Save,
  Truck,
} from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  draftLowStockPurchaseOrders,
  fetchAdminProducts,
  fetchSupplierOverview,
  updateAdminProductCost,
} from "../../services/api.js";

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function SupplierManager({ canWrite = false }) {
  const [overview, setOverview] = useState({ categories: [], low_stock: [], purchase_orders: [] });
  const [products, setProducts] = useState([]);
  const [costDrafts, setCostDrafts] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [supplierData, productData] = await Promise.all([
        fetchSupplierOverview(),
        fetchAdminProducts(),
      ]);
      setOverview(supplierData);
      setProducts(productData);
      setCostDrafts(Object.fromEntries(productData.map((product) => [product.id, String(product.unitCost ?? 0)])));
    } catch (loadError) {
      setError(loadError.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveCost = async (product) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const cost = Number(costDrafts[product.id]);
      if (!Number.isFinite(cost) || cost < 0) throw new Error("Enter a valid non-negative unit cost.");
      await updateAdminProductCost(product.id, cost);
      setMessage(`Unit cost saved for ${product.name}.`);
      await load();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  };

  const draftOrders = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await draftLowStockPurchaseOrders();
      setMessage(
        `${result.created.length} draft purchase order(s) generated${
          result.skipped_missing_cost
            ? `; ${result.skipped_missing_cost} low-stock product(s) skipped until unit cost is entered`
            : ""
        }.`,
      );
      await load();
    } catch (draftError) {
      setError(draftError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-ops-stack">
      {error && <div className="admin-ops-error" role="alert"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="admin-ops-success" role="status"><PackageCheck size={16} />{message}</div>}
      {!canWrite && <p className="admin-ops-note">Your role has read-only access to supplier costs and purchase-order drafts.</p>}
      <section className="admin-ops-margin-grid">
        {overview.categories.map((category) => (
          <article className="admin-panel admin-ops-margin-card" key={category.category}>
            <span className="admin-overline">CATEGORY MARGIN</span>
            <h2>{category.category}</h2>
            {category.gross_margin_percent === null
              ? <strong className="admin-ops-margin-na">Add product costs</strong>
              : <strong>{category.gross_margin_percent}% <small>gross margin</small></strong>}
            <p>{category.costed_products} of {category.products} products have a unit cost</p>
          </article>
        ))}
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">COST OF GOODS SOLD</span><h2>Product cost register</h2></div>
          <button className="admin-button secondary" onClick={load} disabled={busy}><RefreshCw size={14} />Refresh</button>
        </header>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Product</th><th>Category</th><th>Retail price</th><th>Unit cost (KSh)</th><th>Gross margin</th><th>Save</th></tr></thead>
            <tbody>{products.map((product) => {
              const cost = Number(costDrafts[product.id] ?? 0);
              const margin = product.price > 0 && cost > 0
                ? ((product.price - cost) / product.price) * 100
                : null;
              return (
                <tr key={product.id}>
                  <td><strong>{product.name}</strong><small className="admin-stock-threshold">{product.sku}</small></td>
                  <td>{product.category}</td>
                  <td>{formatKsh(product.price)}</td>
                  <td><input className="admin-ops-cost-input" type="number" min="0" step="0.01" value={costDrafts[product.id] ?? ""} disabled={!canWrite} onChange={(event) => setCostDrafts((current) => ({ ...current, [product.id]: event.target.value }))} /></td>
                  <td>{margin === null ? <span className="admin-ops-muted">Cost not set</span> : <strong className={margin < 0 ? "admin-ops-negative" : ""}>{margin.toFixed(1)}%</strong>}</td>
                  <td><button className="admin-button secondary small" onClick={() => saveCost(product)} disabled={!canWrite || busy}><Save size={13} />Save cost</button></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">REPLENISHMENT WORKFLOW</span><h2>Low-stock purchase orders <small>{overview.low_stock.length} products at or below threshold</small></h2></div>
          <button className="admin-button primary" onClick={draftOrders} disabled={!canWrite || busy || !overview.low_stock.length}><Truck size={15} />{busy ? "Working…" : "Draft low-stock POs"}</button>
        </header>
        <p className="admin-ops-note"><Boxes size={14} />Creates editable draft records using three times the alert threshold as the target stock. Drafts are not sent to suppliers.</p>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Product</th><th>Stock</th><th>Alert threshold</th><th>Unit cost</th><th>Suggested quantity</th><th>Est. cost</th></tr></thead>
            <tbody>{overview.low_stock.map((product) => {
              const quantity = Math.max(1, product.low_stock_threshold * 3 - product.stock);
              return <tr key={product.id}><td><strong>{product.name}</strong></td><td>{product.stock}</td><td>{product.low_stock_threshold}</td><td>{product.unit_cost ? formatKsh(product.unit_cost) : <span className="admin-ops-muted">Not set</span>}</td><td>{quantity}</td><td>{product.unit_cost ? formatKsh(quantity * product.unit_cost) : "—"}</td></tr>;
            })}
            {!overview.low_stock.length && <tr><td className="admin-empty-copy" colSpan="6">No products currently need replenishment.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading"><div><span className="admin-overline">PROCUREMENT HISTORY</span><h2>Draft purchase orders</h2></div><ClipboardList size={19} className="admin-ops-rose-icon" /></header>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>PO</th><th>Product</th><th>Quantity</th><th>Unit cost</th><th>Total cost</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{overview.purchase_orders.map((order) => (
              <tr key={order.id}><td><strong>PO-{String(order.id).padStart(5, "0")}</strong></td><td>{order.product_name}</td><td>{order.quantity}</td><td>{formatKsh(order.unit_cost)}</td><td>{formatKsh(order.total_cost)}</td><td><span className="admin-ops-payment-state not_processed">{order.status}</span></td><td>{formatTime(order.created_at)}</td></tr>
            ))}
            {!overview.purchase_orders.length && <tr><td className="admin-empty-copy" colSpan="7">Generated purchase-order drafts will appear here.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
