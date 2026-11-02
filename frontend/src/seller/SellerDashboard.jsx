import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Box,
  ChartNoAxesCombined,
  Download,
  CircleDollarSign,
  LayoutDashboard,
  LogOut,
  Search,
  Package,
  Settings,
  Plus,
  Store,
  Star,
  Trash2,
  X,
  Users,
  MessageSquareText,
  Truck,
  ShieldCheck,
  FileText,
  Tags,
  MapPinned,
  RefreshCw,
  Mail,
  Lightbulb,
  Menu,
} from "lucide-react";
import { formatKsh } from "../data/currency.js";
import ProductImage from "../components/ProductImage.jsx";
import {
  AGRICULTURE_BUSINESS_TYPE,
  AGRICULTURE_POLICY,
  BUSINESS_TYPES,
} from "../data/businessTypes.js";
import {
  createSellerProduct,
  deleteSellerProduct,
  fetchSellerDashboard,
  fetchSellerMe,
  fetchSellerPortalStatus,
  fetchSellerOrders,
  fetchSellerPayouts,
  fetchSellerProducts,
  approveSellerSelf,
  bulkUpdateSellerProducts,
  registerSeller,
  requestSellerProfileUpdate,
  simulateSellerPayout,
  sellerLogin,
  sellerLogout,
  uploadSellerImage,
  updateSellerProfile,
  updateSellerOrder,
  updateSellerProduct,
  upgradeSellerPlan,
  verifySellerProfileUpdate,
} from "../services/api.js";
import SellerAdvancedTools, {
  BulkProductManager,
} from "./SellerAdvancedTools.jsx";
import SellerOperations, {
  SellerNotificationSettings,
} from "./components/SellerOperations.jsx";
import OrderFulfillment from "./components/OrderFulfillment.jsx";
import "./Marketplace.css";

const emptyRegistration = {
  email: "",
  password: "",
  store_name: "",
  owner_name: "",
  logo_url: "",
  banner_url: "",
  business_phone: "",
  business_type: BUSINESS_TYPES[1],
  business_category: BUSINESS_TYPES[1],
  whatsapp_number: "",
  payout_method: "M-Pesa",
  payout_account: "",
  submitted_documents: "",
};
const emptyProduct = {
  name: "",
  brand: "",
  sku: "",
  category: "Perfumes & Fragrances",
  detail: "",
  description: "",
  price: "",
  stock: "10",
  lowStockThreshold: "5",
  images: "",
  tags: "",
  variants: "",
};
const categories = [
  "Beauty & Cosmetics",
  "Electronics",
  "Fashion & Clothing",
  "Home & Furniture",
  "Groceries & Food",
  "Phones & Accessories",
  "Baby & Kids",
  "Sports & Outdoors",
  "Automotive",
  "Agriculture & Garden",
  "Computers & Accessories",
  "Health & Personal Care",
  "Books & Stationery",
  "Kitchen & Dining",
  "Travel & Luggage",
  "Lighting & Electrical",
  "Pet Supplies",
  "Musical Instruments",
  "Veterinary Medicines",
  "Dairy Cattle",
  "Goats & Sheep",
  "Poultry & Fowl",
  "Perfumes & Fragrances",
  "Press-On Nails",
  "Skincare & Glow",
  "Lip & Makeup Essentials",
  "Hair & Accessories",
];
const nextFulfillment = {
  PENDING: ["PROCESSING", "Mark packed"],
  PROCESSING: ["SHIPPED", "Dispatch with courier"],
  SHIPPED: ["DELIVERED", "Mark delivered"],
};
const fulfillmentLabels = {
  PENDING: "Payment Escrowed",
  PROCESSING: "Packing in Progress",
  SHIPPED: "Dispatched to Courier",
  DELIVERED: "Delivered",
};
const DEMO_SELLER = {
  id: 0,
  store_name: "Maison Demo Atelier",
  store_slug: "maison-demo-atelier",
  store_bio: "A curated demo boutique for the Maison Muse seller portal.",
  business_category: "Perfumes & Fragrances",
  business_phone: "0712345678",
  whatsapp_phone: "0712345678",
  instagram_url: "",
  tiktok_url: "",
  operating_hours: "Mon–Sat, 9:00–18:00",
  holiday_mode: false,
  payout_method: "M-Pesa",
  payout_account: "0712345678",
  status: "APPROVED",
  selected_plan: "pro",
  commission_rate: 5,
  rating: 4.9,
};
const DEMO_PRODUCTS = [
  {
    id: "demo-product-1",
    name: "Amber Veil Eau de Parfum",
    brand: "Maison Demo Atelier",
    sku: "DEMO-AMBER-01",
    category: "Perfumes & Fragrances",
    price: 4200,
    stock: 12,
    lowStockThreshold: 5,
    image: "https://images.unsplash.com/photo-1594035910387-fea47794261f?auto=format&fit=crop&w=300&q=80",
    gallery: [],
    tags: ["amber", "best seller"],
  },
];
const DEMO_METRICS = {
  gross_sales: 18400,
  net_earnings: 17480,
  total_items_sold: 6,
  pending_orders: 2,
  low_stock_alerts: 1,
  product_count: 8,
  average_rating: 4.9,
  selected_plan: "pro",
  commission_rate: 5,
  available_balance: 3200,
};
const PLAN_NAMES = {
  boutique: "Boutique Starter",
  pro: "Pro Beauty Studio",
  enterprise: "Enterprise Brand",
};
const storefrontUpdatePayload = ({ business_email, ...settings }) => ({
  ...settings,
  payout_account: settings.payout_method === "M-Pesa"
    ? settings.business_phone
    : settings.payout_account,
  email: business_email ?? "",
});

function ProductEditor({ product, onClose, onSave, onUploadImage, saving }) {
  const [form, setForm] = useState(() => product ? {
    ...product,
    price: String(product.price),
    stock: String(product.stock),
    lowStockThreshold: String(product.lowStockThreshold ?? 5),
    images: (product.gallery ?? [product.image]).join("\n"),
    tags: (product.tags ?? []).join(", "),
    variants: (product.variants ?? [])
      .map((variant) => `${variant.name}: ${variant.options.join(", ")}`)
      .join("\n"),
  } : emptyProduct);
  const [error, setError] = useState("");
  const [uploadingImage, setUploadingImage] = useState(false);
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const uploadProductImage = async (file) => {
    if (!file) return;
    if (form.images.split(/\r?\n/).filter(Boolean).length >= 4) {
      setError("Each product can have up to four images.");
      return;
    }
    setUploadingImage(true);
    setError("");
    try {
      const imageUrl = await onUploadImage(file);
      setForm((current) => ({
        ...current,
        images: [...current.images.split(/\r?\n/).filter(Boolean), imageUrl].join("\n"),
      }));
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploadingImage(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    const images = form.images.split(/\r?\n/).map((image) => image.trim()).filter(Boolean);
    if (images.length > 4) {
      setError("Each product can have up to four images.");
      return;
    }
    if (!images.length || images.some((image) =>
      !image.startsWith("https://") &&
      !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/uploads\//.test(image)
    )) {
      setError("Enter an HTTPS image URL or upload an image from this device.");
      return;
    }
    const variants = [];
    for (const line of form.variants.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)) {
      const separator = line.indexOf(":");
      const name = separator >= 0 ? line.slice(0, separator).trim() : "";
      const options = separator >= 0
        ? line.slice(separator + 1).split(",").map((value) => value.trim()).filter(Boolean)
        : [];
      if (!name || !options.length) {
        setError("Enter product variants as one option group per line, for example Size: 30ml, 50ml.");
        return;
      }
      variants.push({ name, options });
    }
    try {
      await onSave({
        name: form.name,
        brand: form.brand,
        sku: form.sku,
        category: form.category,
        detail: form.detail,
        description: form.description,
        price: Number(form.price),
        stock: Number(form.stock),
        lowStockThreshold: Number(form.lowStockThreshold),
        images,
        tags: form.tags.split(/[,\r\n]/).map((tag) => tag.trim()).filter(Boolean),
        variants,
      });
    } catch (saveError) {
      setError(saveError.message);
    }
  };

  return (
    <div className="marketplace-modal-backdrop" onMouseDown={onClose}>
      <section
        className="marketplace-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="seller-product-form-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div><span className="marketplace-eyebrow">YOUR INVENTORY</span><h2 id="seller-product-form-title">{product ? "Edit product" : "Add a product"}</h2></div>
          <button type="button" className="marketplace-icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </header>
        <form onSubmit={submit}>
          <div className="marketplace-form-grid">
            <label>Product name<input required minLength={2} value={form.name} onChange={(event) => update("name", event.target.value)} /></label>
            <label>Brand<input required value={form.brand} onChange={(event) => update("brand", event.target.value)} /></label>
            <label>Category<select value={form.category} onChange={(event) => update("category", event.target.value)}>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
            <label>SKU<input required pattern="[A-Za-z0-9._-]+" value={form.sku} onChange={(event) => update("sku", event.target.value)} /></label>
            <label>Price (KSh)<input type="number" min="1" step="1" required value={form.price} onChange={(event) => update("price", event.target.value)} /></label>
            <label>Stock<input type="number" min="0" required value={form.stock} onChange={(event) => update("stock", event.target.value)} /></label>
            <label>Low-stock alert<input type="number" min="0" required value={form.lowStockThreshold} onChange={(event) => update("lowStockThreshold", event.target.value)} /></label>
            <label className="marketplace-form-wide">Short description<input required minLength={5} value={form.detail} onChange={(event) => update("detail", event.target.value)} /></label>
            <label className="marketplace-form-wide">Description<textarea required minLength={10} rows="3" value={form.description} onChange={(event) => update("description", event.target.value)} /></label>
            <label className="marketplace-form-wide">Upload product images from your computer or phone<input type="file" accept="image/jpeg,image/png,image/webp" disabled={saving || uploadingImage} onChange={(event) => { void uploadProductImage(event.target.files?.[0]); event.target.value = ""; }} /></label>
            <label className="marketplace-form-wide">Image URLs (one per line)<textarea required rows="3" value={form.images} onChange={(event) => update("images", event.target.value)} /></label>
            <div className="marketplace-form-wide seller-image-previews" aria-label="Product image previews">
              {form.images.split(/\r?\n/).map((image) => image.trim()).filter(Boolean).map((image, index) => (
                <figure key={`${image}-${index}`}>
                  <ProductImage src={image} alt={`Product image ${index + 1} preview`} />
                  <figcaption>
                    <span>Image {index + 1}</span>
                    <button
                      type="button"
                      className="seller-image-remove"
                      aria-label={`Remove product image ${index + 1}`}
                      onClick={() => update(
                        "images",
                        form.images.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
                          .filter((_, imageIndex) => imageIndex !== index)
                          .join("\n"),
                      )}
                    >
                      Remove
                    </button>
                  </figcaption>
                </figure>
              ))}
            </div>
            <label className="marketplace-form-wide">Tags (comma separated)<input value={form.tags} onChange={(event) => update("tags", event.target.value)} placeholder="vegan, best seller, gift" /></label>
            <label className="marketplace-form-wide">Variants (one group per line)<textarea rows="3" value={form.variants} onChange={(event) => update("variants", event.target.value)} placeholder={"Size: 30ml, 50ml, 100ml\nShape: Almond, Coffin, Short Square"} /></label>
          </div>
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <footer><button type="button" className="marketplace-button secondary" onClick={onClose}>Cancel</button><button type="submit" className="marketplace-button primary" disabled={saving}>{saving ? "Saving…" : "Save product"}</button></footer>
        </form>
      </section>
    </div>
  );
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function downloadPackingSlip(order, seller) {
  const { default: QRCode } = await import("qrcode");
  const qrSvg = await QRCode.toString(
    `MAISON-MUSE|${order.order_number}|${order.tracking_number || "NOT-DISPATCHED"}`,
    { type: "svg", errorCorrectionLevel: "M", margin: 1, width: 180 },
  );
  const itemRows = order.items.map((item) =>
    `<tr><td>${escapeHtml(item.product_name)}</td><td>${escapeHtml(item.variant || "—")}</td><td>${item.quantity}</td></tr>`,
  ).join("");
  const logo = seller.logo_url
    ? `<img class="logo" src="${escapeHtml(seller.logo_url)}" alt="${escapeHtml(seller.store_name)} logo">`
    : "";
  const documentText = `<!doctype html><html><head><meta charset="utf-8"><title>Packing slip ${escapeHtml(order.order_number)}</title><style>body{font:16px Arial,sans-serif;max-width:760px;margin:48px auto;padding:0 20px;color:#26313b}.brand{display:flex;align-items:center;gap:16px}.logo{width:72px;height:72px;object-fit:contain}h1{font-size:24px}table{width:100%;border-collapse:collapse;margin:24px 0}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd}small{color:#667}.dispatch{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #ddd;padding-top:18px}.qr{width:140px;height:140px}.print{float:right;padding:8px 14px}@media print{.print{display:none}body{margin:0 auto}}</style></head><body><button class="print" onclick="window.print()">Print packing slip</button><div class="brand">${logo}<h1>${escapeHtml(seller.store_name)} · Packing slip</h1></div><p>Order ${escapeHtml(order.order_number)}</p><p>Ship to: ${escapeHtml(order.customer.name)}<br>${escapeHtml(order.customer.phone)}<br>${escapeHtml(order.customer.address)}</p><table><thead><tr><th>Item</th><th>Variant</th><th>Qty</th></tr></thead><tbody>${itemRows}</tbody></table><small>Seller subtotal: ${formatKsh(order.subtotal)}</small><div class="dispatch"><div><strong>Dispatch details</strong><p>Courier: ${escapeHtml(order.courier_name || "Not assigned")}<br>Tracking: ${escapeHtml(order.tracking_number || "Not dispatched")}</p></div><div class="qr">${qrSvg}</div></div></body></html>`;
  const url = URL.createObjectURL(new Blob([documentText], { type: "text/html" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `packing-slip-${order.order_number}.html`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadCsv(filename, rows) {
  const csv = rows.map((row) =>
    row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","),
  ).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadMonthlyEarningsReport(seller, orders) {
  const month = new Date().toISOString().slice(0, 7);
  const monthlyOrders = orders.filter((order) =>
    order.ordered_at?.startsWith(month) &&
    ["paid", "completed_demo"].includes(order.payment_status),
  );
  const rows = [
    ["Maison Muse Seller Earnings Report", seller.store_name],
    ["Reporting month", month],
    ["VAT", "Not calculated by Maison Muse; consult your tax adviser"],
    [],
    ["Order", "Date", "Gross (KSh)", "Platform commission (KSh)", "Net earnings (KSh)", "Payment status"],
    ...monthlyOrders.map((order) => [
      order.order_number,
      new Date(order.ordered_at).toLocaleDateString(),
      order.subtotal,
      order.commission_amount,
      order.seller_payout_amount,
      order.payment_status,
    ]),
  ];
  downloadCsv(`maison-muse-earnings-${month}.csv`, rows);
}

function SellerDashboard() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [seller, setSeller] = useState(null);
  const [checking, setChecking] = useState(true);
  const [portalMaintenance, setPortalMaintenance] = useState(null);
  const [portalStatusError, setPortalStatusError] = useState("");
  const [demoMode, setDemoMode] = useState(false);
  const [activeTab, setActiveTab] = useState(() => {
    try {
      return window.localStorage.getItem("seller_studio_active_tab") ?? "overview";
    } catch {
      return "overview";
    }
  });
  const [mode, setMode] = useState("register");
  const [registration, setRegistration] = useState(emptyRegistration);
  const [credentials, setCredentials] = useState({ email: "", password: "" });
  const [dashboard, setDashboard] = useState(null);
  const [analyticsPeriod, setAnalyticsPeriod] = useState("30d");
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [productSearch, setProductSearch] = useState("");
  const [productCategory, setProductCategory] = useState("All categories");
  const [productStatusFilter, setProductStatusFilter] = useState("All statuses");
  const [selectedProductIds, setSelectedProductIds] = useState([]);
  const [bulkStatus, setBulkStatus] = useState("ACTIVE");
  const [bulkDiscount, setBulkDiscount] = useState("10");
  const [productPreview, setProductPreview] = useState(null);
  const [dispatchDetails, setDispatchDetails] = useState({});
  const [payoutForm, setPayoutForm] = useState({
    amount: "500",
    destination_type: "registered_phone",
    destination: "",
  });
  const [settingsForm, setSettingsForm] = useState(null);
  const [profileVerificationCode, setProfileVerificationCode] = useState("");
  const [profileVerificationPending, setProfileVerificationPending] = useState(false);
  const [productModal, setProductModal] = useState(null);
  const [planSelection, setPlanSelection] = useState("boutique");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [sidebarOpen]);

  useEffect(() => {
    try {
      window.localStorage.setItem("seller_studio_active_tab", activeTab);
    } catch {
      setError("Your selected dashboard tab could not be saved in this browser.");
    }
  }, [activeTab]);

  const loadSellerData = useCallback(async (profile) => {
    setSeller(profile);
    setPlanSelection(profile.selected_plan ?? "boutique");
    setSettingsForm({
      store_name: profile.store_name ?? "",
      business_email: profile.email ?? "",
      store_bio: profile.store_bio ?? "",
      business_category: profile.business_category || categories[0],
      logo_url: profile.logo_url ?? "",
      banner_url: profile.banner_url ?? "",
      business_phone: profile.business_phone ?? "",
      whatsapp_phone: profile.whatsapp_phone ?? profile.business_phone ?? "",
      instagram_url: profile.instagram_url ?? "",
      tiktok_url: profile.tiktok_url ?? "",
      operating_hours: profile.operating_hours ?? "",
      holiday_mode: Boolean(profile.holiday_mode),
      payout_method: profile.payout_method ?? "M-Pesa",
      payout_account: profile.payout_account ?? "",
    });
    setError("");
    if (profile.status !== "APPROVED") {
      setDashboard(null);
      setProducts([]);
      setOrders([]);
      setPayouts([]);
      return;
    }
    const [metrics, sellerProducts, sellerOrders, sellerPayouts] = await Promise.all([
      fetchSellerDashboard(),
      fetchSellerProducts(),
      fetchSellerOrders(),
      fetchSellerPayouts(),
    ]);
    setDashboard(metrics);
    setProducts(sellerProducts);
    setOrders(sellerOrders);
    setPayouts(sellerPayouts);
  }, []);

  useEffect(() => {
    let active = true;
    let portalStatusLoaded = false;
    const loadPortal = async () => {
      try {
        const status = await fetchSellerPortalStatus();
        portalStatusLoaded = true;
        if (!active) return;
        setPortalStatusError("");
        if (status.enabled) {
          setPortalMaintenance(status);
          return;
        }
        setPortalMaintenance(null);
        const profile = await fetchSellerMe();
        if (active) {
          setDemoMode(false);
          await loadSellerData(profile);
        }
      } catch (loadError) {
        if (!active) return;
        if (!portalStatusLoaded) {
          setPortalStatusError(loadError.message);
          return;
        }
        if (loadError.status === 503) {
          try {
            const status = await fetchSellerPortalStatus();
            if (status.enabled) {
              setPortalMaintenance(status);
              return;
            }
          } catch (statusError) {
            setPortalStatusError(statusError.message);
            return;
          }
        }
        setDemoMode(true);
        setSeller(DEMO_SELLER);
        setDashboard(DEMO_METRICS);
        setProducts(DEMO_PRODUCTS);
        setOrders([]);
        setPayouts([
          {
            id: "demo-payout",
            date: new Date().toISOString(),
            reference: "DEMO-MPESA-QX8923KLM",
            transaction_id: "SIMULATED-QX8923KLM",
            gross_amount: 3368,
            net_paid: 3200,
            payout_method: "M-Pesa",
            status: "COMPLETED",
            is_demo: true,
          },
        ]);
        setSettingsForm({
          store_name: DEMO_SELLER.store_name,
          business_email: "",
          store_bio: DEMO_SELLER.store_bio,
          business_category: DEMO_SELLER.business_category,
          logo_url: "",
          banner_url: "",
          business_phone: DEMO_SELLER.business_phone,
          whatsapp_phone: DEMO_SELLER.whatsapp_phone,
          instagram_url: DEMO_SELLER.instagram_url,
          tiktok_url: DEMO_SELLER.tiktok_url,
          operating_hours: DEMO_SELLER.operating_hours,
          holiday_mode: DEMO_SELLER.holiday_mode,
          payout_method: DEMO_SELLER.payout_method,
          payout_account: DEMO_SELLER.payout_account,
        });
        if (loadError.status !== 401) setError(loadError.message);
      } finally {
        if (active) setChecking(false);
      }
    };
    void loadPortal();
    return () => { active = false; };
  }, [loadSellerData]);

  useEffect(() => {
    let active = true;
    const checkPortalMaintenance = async () => {
      try {
        const status = await fetchSellerPortalStatus();
        if (!active) return;
        setPortalStatusError("");
        setPortalMaintenance(status.enabled ? status : null);
      } catch (statusError) {
        if (active) setPortalStatusError(statusError.message);
      }
    };
    const intervalId = window.setInterval(checkPortalMaintenance, 5000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (demoMode || seller?.status !== "APPROVED") return undefined;
    let active = true;
    fetchSellerDashboard(analyticsPeriod)
      .then((metrics) => {
        if (active) setDashboard(metrics);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      });
    return () => { active = false; };
  }, [analyticsPeriod, demoMode, seller?.id, seller?.status]);

  useEffect(() => {
    if (demoMode || seller?.status !== "APPROVED" || activeTab !== "overview") {
      return undefined;
    }
    let active = true;
    const refreshMetrics = async () => {
      try {
        const metrics = await fetchSellerDashboard(analyticsPeriod);
        if (active) setDashboard(metrics);
      } catch (loadError) {
        if (active) setError(loadError.message);
      }
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshMetrics();
    };
    const intervalId = window.setInterval(refreshMetrics, 15000);
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [activeTab, analyticsPeriod, demoMode, seller?.id, seller?.status]);

  useEffect(() => {
    if (demoMode || seller?.status !== "APPROVED" || activeTab !== "orders") return undefined;
    let active = true;
    const refreshOrders = async () => {
      try {
        const [latestOrders, latestDashboard] = await Promise.all([
          fetchSellerOrders(),
          fetchSellerDashboard(analyticsPeriod),
        ]);
        if (active) {
          setOrders(latestOrders);
          setDashboard(latestDashboard);
        }
      } catch (refreshError) {
        if (active) setError(refreshError.message);
      }
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshOrders();
    };
    void refreshOrders();
    const intervalId = window.setInterval(refreshOrders, 5000);
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [activeTab, analyticsPeriod, demoMode, seller?.status]);

  const openAccessForm = (nextMode = "login") => {
    setDemoMode(false);
    setSeller(null);
    setMode(nextMode);
    setError("");
  };

  const submitRegistration = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const profile = await registerSeller({
        ...registration,
        submitted_documents: registration.submitted_documents
          .split(/\r?\n/)
          .map((url) => url.trim())
          .filter(Boolean),
      });
      await loadSellerData(profile);
      setNotice("Your seller application is submitted and waiting for verification.");
    } catch (registerError) {
      setError(registerError.message);
    } finally {
      setSaving(false);
    }
  };

  const submitLogin = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await sellerLogin(credentials.email, credentials.password);
      await loadSellerData(await fetchSellerMe());
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    try {
      if (!demoMode) await sellerLogout();
      const savedUser = JSON.parse(
        window.localStorage.getItem("user_profile") ??
          window.localStorage.getItem("mm-auth-user") ??
          "null",
      );
      if (demoMode || savedUser?.role === "seller") {
        [
          "auth_token",
          "user_profile",
          "mm-auth-token",
          "mm-auth-user",
          "mm-auth-expires-at",
        ].forEach((key) => window.localStorage.removeItem(key));
      }
      setSeller(null);
      setDashboard(null);
      setProducts([]);
      setOrders([]);
      setPayouts([]);
      if (demoMode) openAccessForm("login");
    } catch (logoutError) {
      setError(logoutError.message);
    }
  };

  const unlockSellerStudio = async () => {
    setSaving(true);
    setError("");
    try {
      const approvedSeller = await approveSellerSelf();
      const savedProfile = JSON.parse(
        window.localStorage.getItem("user_profile") ??
          window.localStorage.getItem("mm-auth-user") ??
          "{}",
      );
      const updatedProfile = {
        ...savedProfile,
        role: "seller",
        status: "APPROVED",
        seller: {
          ...(savedProfile.seller ?? {}),
          id: approvedSeller.id,
          store_name: approvedSeller.store_name,
          store_slug: approvedSeller.store_slug,
          status: "APPROVED",
        },
      };
      window.localStorage.setItem("user_profile", JSON.stringify(updatedProfile));
      await loadSellerData(approvedSeller);
      setNotice("Development approval is saved. Seller Studio is unlocked.");
    } catch (approvalError) {
      setError(approvalError.message);
    } finally {
      setSaving(false);
    }
  };

  const applyBulkAction = async (action, value) => {
    if (!selectedProductIds.length) return;
    setSaving(true);
    setError("");
    try {
      const result = await bulkUpdateSellerProducts({
        product_ids: selectedProductIds,
        action,
        ...(action === "status" ? { status: value } : action === "discount"
          ? { discount_percent: Number(value) }
          : {}),
      });
      setProducts((current) => current.map((product) =>
        result.products.find((updated) => updated.id === product.id) ?? product,
      ));
      setSelectedProductIds([]);
      setNotice(action === "status"
        ? "Selected product statuses were updated."
        : action === "discount"
          ? "A bulk price discount was applied."
          : "Selected products were marked out of stock.");
    } catch (bulkError) {
      setError(bulkError.message);
    } finally {
      setSaving(false);
    }
  };

  const saveProduct = async (product) => {
    setSaving(true);
    try {
      const isUpdate = Boolean(productModal?.id);
      if (isUpdate) await updateSellerProduct(productModal.id, product);
      else await createSellerProduct(product);
      setProducts(await fetchSellerProducts());
      setDashboard(await fetchSellerDashboard(analyticsPeriod));
      setProductModal(null);
      setNotice(isUpdate
        ? "Your product inventory has been updated."
        : "Your listing was saved as a draft and submitted for QC. Buyers can see it after administrator approval.");
    } finally {
      setSaving(false);
    }
  };

  const uploadProductImage = async (file) => {
    setSaving(true);
    setError("");
    try {
      const result = await uploadSellerImage(file);
      setNotice("Product image uploaded and added to your listing.");
      return result.url;
    } finally {
      setSaving(false);
    }
  };

  const savePlanSelection = async () => {
    setSaving(true);
    setError("");
    try {
      const { seller: updatedSeller, subscription } = await upgradeSellerPlan({
        selected_plan: planSelection,
        phone_number: seller.payout_account ?? "",
      });
      setSeller((current) => ({ ...current, ...updatedSeller }));
      setDashboard((current) => ({
        ...current,
        selected_plan: updatedSeller.selected_plan,
        commission_rate: updatedSeller.commission_rate,
      }));
      setNotice(
        `${subscription.payment_method} completed · ${subscription.reference}. This is a demo payment and no M-Pesa charge was sent.`,
      );
    } catch (planError) {
      setError(planError.message);
    } finally {
      setSaving(false);
    }
  };

  const removeProduct = async (product) => {
    if (!window.confirm(`Remove "${product.name}" from your store?`)) return;
    setError("");
    try {
      await deleteSellerProduct(product.id);
      setProducts((current) => current.filter((item) => item.id !== product.id));
      setDashboard(await fetchSellerDashboard(analyticsPeriod));
      setNotice("Product removed from your storefront.");
    } catch (removeError) {
      setError(removeError.message);
    }
  };

  const advanceOrder = async (order) => {
    const [nextStatus] = nextFulfillment[order.fulfillment_status] ?? [];
    if (!nextStatus) return;
    const dispatch = dispatchDetails[order.id] ?? {
      courier_name: order.courier_name ?? "",
      tracking_number: order.tracking_number ?? "",
    };
    if (nextStatus === "SHIPPED" && (!dispatch.courier_name || !dispatch.tracking_number)) {
      setError("Choose a courier and enter its tracking number before dispatch.");
      return;
    }
    try {
      await updateSellerOrder(order.id, nextStatus, dispatch);
      setOrders((current) => current.map((item) =>
        item.id === order.id
          ? {
              ...item,
              fulfillment_status: nextStatus,
              courier_name: dispatch.courier_name,
              tracking_number: dispatch.tracking_number,
            }
          : item,
      ));
      setDashboard(await fetchSellerDashboard(analyticsPeriod));
    } catch (updateError) {
      setError(updateError.message);
    }
  };

  const saveStorefrontSettings = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const emailChanged = settingsForm.business_email.trim().toLowerCase() !==
        String(seller.email ?? "").trim().toLowerCase();
      const phoneChanged = settingsForm.business_phone.replace(/\D/g, "") !==
        String(seller.business_phone ?? "").replace(/\D/g, "");
      if (emailChanged || phoneChanged) {
        await requestSellerProfileUpdate({
          ...(emailChanged ? { new_email: settingsForm.business_email.trim() } : {}),
          ...(phoneChanged ? { new_phone: settingsForm.business_phone.trim() } : {}),
        });
        setProfileVerificationPending(true);
        setProfileVerificationCode("");
        setNotice("A 6-digit confirmation code has been sent to your email. Verify it to apply the contact change.");
        return;
      }
      const updatedSeller = await updateSellerProfile(storefrontUpdatePayload(settingsForm));
      setSeller(updatedSeller);
      setNotice("Your boutique branding, contact details, hours, and payout details have been saved.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const confirmSellerProfileUpdate = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const verification = await verifySellerProfileUpdate(profileVerificationCode);
      const updatedSeller = await updateSellerProfile(storefrontUpdatePayload(settingsForm));
      setSeller({ ...updatedSeller, ...verification.seller });
      setSettingsForm((current) => ({
        ...current,
        business_email: verification.seller.email ?? current.business_email,
        business_phone: verification.seller.business_phone ?? current.business_phone,
      }));
      setProfileVerificationPending(false);
      setProfileVerificationCode("");
      setNotice("Your contact details were verified, and boutique settings were saved.");
    } catch (verificationError) {
      setError(verificationError.message);
    } finally {
      setSaving(false);
    }
  };

  const uploadStoreAsset = async (field, file) => {
    if (!file) return;
    setSaving(true);
    setError("");
    try {
      const result = await uploadSellerImage(file);
      setSettingsForm((current) => ({ ...current, [field]: result.url }));
      setNotice("Store image uploaded. Save storefront settings to publish it.");
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setSaving(false);
    }
  };

  const requestDemoPayout = async (requestedAmount = Number(payoutForm.amount)) => {
    setSaving(true);
    setError("");
    try {
      const payout = await simulateSellerPayout({
        amount: requestedAmount,
        destination_type: payoutForm.destination_type,
        ...(payoutForm.destination_type === "registered_phone"
          ? {}
          : { destination: payoutForm.destination }),
      });
      const [nextDashboard, nextPayouts] = await Promise.all([
        fetchSellerDashboard(analyticsPeriod),
        fetchSellerPayouts(),
      ]);
      setDashboard(nextDashboard);
      setPayouts(nextPayouts);
      setNotice(`${payout.message} ${payout.destination_hint} · Reference: ${payout.transaction_id}`);
      setPayoutForm((current) => ({
        ...current,
        amount: Math.min(500, nextDashboard.available_balance).toFixed(2),
      }));
    } catch (payoutError) {
      setError(payoutError.message);
    } finally {
      setSaving(false);
    }
  };

  if (checking) return <main className="seller-auth-screen"><p>Preparing your seller portal…</p></main>;
  if (portalStatusError) {
    return (
      <main className="seller-suspension-screen">
        <section className="seller-suspension-card" role="alert">
          <span className="marketplace-eyebrow">SELLER ACCOUNT ACCESS</span>
          <h1>Seller Portal availability could not be checked</h1>
          <p>{portalStatusError}</p>
          <button type="button" className="marketplace-button secondary" onClick={() => window.location.reload()}>Try again</button>
        </section>
      </main>
    );
  }
  if (portalMaintenance?.enabled) {
    return (
      <main className="seller-suspension-screen">
        <header className="seller-topbar">
          <Link className="marketplace-brand" to="/">maison <span>muse.</span></Link>
        </header>
        <section className="seller-suspension-card" role="status">
          <span className="seller-suspension-icon"><Store size={25} /></span>
          <span className="marketplace-eyebrow">SELLER PORTAL ACCESS</span>
          <h1>Seller Studio is temporarily unavailable</h1>
          <p>Maison Muse has temporarily paused access for all sellers while platform maintenance is in progress.</p>
          {portalMaintenance.reason && <div className="seller-suspension-reason"><strong>Maintenance notice</strong><p>{portalMaintenance.reason}</p></div>}
          <Link className="marketplace-button secondary" to="/">Return to storefront</Link>
        </section>
      </main>
    );
  }
  if (!seller) {
    return (
      <main className="seller-auth-screen">
        <form className="seller-auth-card" onSubmit={mode === "register" ? submitRegistration : submitLogin}>
          <Link className="marketplace-brand" to="/">maison <span>muse.</span></Link>
          <span className="marketplace-eyebrow">MAISON MUSE MARKETPLACE</span>
          <h1>{mode === "register" ? "Open your store." : "Welcome back."}</h1>
          <p>{mode === "register" ? "Apply to bring your edit to our community." : "Sign in to manage your seller store."}</p>
          {mode === "register" ? (
            <div className="marketplace-form-grid">
              <label>Email<input type="email" autoComplete="email" required value={registration.email} onChange={(event) => setRegistration((current) => ({ ...current, email: event.target.value }))} /></label>
              <label>Password (12+ characters)<input type="password" autoComplete="new-password" minLength="12" required value={registration.password} onChange={(event) => setRegistration((current) => ({ ...current, password: event.target.value }))} /></label>
              <label>Store name<input required minLength="2" value={registration.store_name} onChange={(event) => setRegistration((current) => ({ ...current, store_name: event.target.value }))} /></label>
              <label>Owner name<input required minLength="2" value={registration.owner_name} onChange={(event) => setRegistration((current) => ({ ...current, owner_name: event.target.value }))} /></label>
              <label>Primary Industry / Business Category
                <select required value={registration.business_type} onChange={(event) => setRegistration((current) => ({ ...current, business_type: event.target.value, business_category: event.target.value }))}>
                  {BUSINESS_TYPES.map((businessType) => <option key={businessType}>{businessType}</option>)}
                </select>
              </label>
              <label>Business phone<input type="tel" required value={registration.business_phone} onChange={(event) => setRegistration((current) => ({ ...current, business_phone: event.target.value }))} /></label>
              {registration.business_type === AGRICULTURE_BUSINESS_TYPE && <>
                <label>Verified WhatsApp Business phone number<input type="tel" required minLength="7" maxLength="32" value={registration.whatsapp_number} onChange={(event) => setRegistration((current) => ({ ...current, whatsapp_number: event.target.value }))} /></label>
                <p className="seller-agriculture-policy" role="note">{AGRICULTURE_POLICY}</p>
              </>}
              <label className="marketplace-form-wide">Logo image URL (HTTPS)<input type="url" placeholder="https://…" value={registration.logo_url} onChange={(event) => setRegistration((current) => ({ ...current, logo_url: event.target.value }))} /></label>
              <label className="marketplace-form-wide">Banner image URL (HTTPS)<input type="url" placeholder="https://…" value={registration.banner_url} onChange={(event) => setRegistration((current) => ({ ...current, banner_url: event.target.value }))} /></label>
              <label className="marketplace-form-wide">Business document preview URLs (one HTTPS URL per line)<textarea rows="3" placeholder="Business registration, ID, or permit preview links" value={registration.submitted_documents} onChange={(event) => setRegistration((current) => ({ ...current, submitted_documents: event.target.value }))} /></label>
              <label>Payout method<select value={registration.payout_method} onChange={(event) => setRegistration((current) => ({ ...current, payout_method: event.target.value }))}><option>M-Pesa</option><option>Bank</option></select></label>
              <label>{registration.payout_method === "M-Pesa" ? "Paybill / Till / phone" : "Bank account details"}<input required value={registration.payout_account} onChange={(event) => setRegistration((current) => ({ ...current, payout_account: event.target.value }))} /></label>
            </div>
          ) : (
            <div className="marketplace-form-grid">
              <label className="marketplace-form-wide">Email<input type="email" autoComplete="username" required value={credentials.email} onChange={(event) => setCredentials((current) => ({ ...current, email: event.target.value }))} /></label>
              <label className="marketplace-form-wide">Password<input type="password" autoComplete="current-password" required value={credentials.password} onChange={(event) => setCredentials((current) => ({ ...current, password: event.target.value }))} /></label>
            </div>
          )}
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          <button type="submit" className="marketplace-button primary" disabled={saving}>{saving ? "Please wait…" : mode === "register" ? "Submit seller application" : "Sign in"} <ArrowRight size={16} /></button>
          <button type="button" className="marketplace-text-button" onClick={() => { setError(""); setMode(mode === "register" ? "login" : "register"); }}>
            {mode === "register" ? "Already a seller? Sign in" : "New to Maison Muse? Apply to sell"}
          </button>
          <Link className="marketplace-back-link" to="/">Return to the storefront</Link>
        </form>
      </main>
    );
  }

  if (seller.status === "SUSPENDED" && !demoMode) {
    return (
      <main className="seller-suspension-screen">
        <header className="seller-topbar">
          <Link className="marketplace-brand" to="/">maison <span>muse.</span></Link>
          <div className="seller-topbar-actions">
            <span className="seller-status-badge suspended">SUSPENDED</span>
            <button type="button" className="marketplace-button secondary" onClick={handleLogout}>
              <LogOut size={15} /> Sign out
            </button>
          </div>
        </header>
        <section className="seller-suspension-card" role="alert">
          <span className="seller-suspension-icon"><Store size={25} /></span>
          <span className="marketplace-eyebrow">SELLER ACCOUNT ACCESS</span>
          <h1>Your seller account is suspended</h1>
          <p>
            Access to Seller Studio, orders, products, payouts, and account tools
            is disabled while this suspension is in effect.
          </p>
          <div className="seller-suspension-reason">
            <strong>Reason provided by Maison Muse</strong>
            <p>{seller.review_note || "Please contact Maison Muse support for details about this suspension."}</p>
          </div>
          <p className="seller-suspension-help">
            If you believe this is a mistake, contact Maison Muse support and
            include your store name: <strong>{seller.store_name}</strong>.
          </p>
          <Link className="marketplace-button secondary" to="/">Return to storefront</Link>
        </section>
      </main>
    );
  }

  if (seller.maintenance_mode && !demoMode) {
    return (
      <main className="seller-suspension-screen">
        <header className="seller-topbar">
          <Link className="marketplace-brand" to="/">maison <span>muse.</span></Link>
          <div className="seller-topbar-actions">
            <span className="seller-status-badge maintenance">MAINTENANCE</span>
            <button type="button" className="marketplace-button secondary" onClick={handleLogout}>
              <LogOut size={15} /> Sign out
            </button>
          </div>
        </header>
        <section className="seller-suspension-card" role="status">
          <span className="seller-suspension-icon"><Store size={25} /></span>
          <span className="marketplace-eyebrow">SELLER ACCOUNT ACCESS</span>
          <h1>Your store is under maintenance</h1>
          <p>Seller Studio tools and public listings are temporarily unavailable while Maison Muse completes this maintenance period.</p>
          <div className="seller-suspension-reason">
            <strong>Reason provided by Maison Muse</strong>
            <p>{seller.maintenance_reason || "Please contact Maison Muse support for more information."}</p>
          </div>
          <p className="seller-suspension-help">Contact Maison Muse support if you need assistance with <strong>{seller.store_name}</strong>.</p>
          <Link className="marketplace-button secondary" to="/">Return to storefront</Link>
        </section>
      </main>
    );
  }

  const navItems = [
    { id: "overview", label: "Overview & Analytics", icon: LayoutDashboard },
    { id: "products", label: "Product Inventory", icon: Package },
    { id: "orders", label: "Order Fulfillment", icon: Box },
    { id: "payouts", label: "Financial Ledger", icon: CircleDollarSign },
    { id: "subscription", label: "Subscription & Membership", icon: CircleDollarSign },
    { id: "promotions", label: "Flash Sales & Promotions", icon: Star },
    { id: "sponsored", label: "Sponsored Ads & Boosting", icon: ChartNoAxesCombined },
    { id: "returns", label: "Returns & Disputes", icon: ArrowRight },
    { id: "team", label: "Staff & Permissions", icon: Users },
    { id: "messages", label: "Customer Messages", icon: MessageSquareText },
    { id: "logistics", label: "Warehouse & Logistics", icon: Truck },
    { id: "quality", label: "Quality Control", icon: ShieldCheck },
    { id: "statement", label: "Weekly Statements", icon: FileText },
    { id: "repricing", label: "Dynamic Repricer", icon: Tags },
    { id: "branches", label: "Branch Inventory", icon: MapPinned },
    { id: "restock", label: "Restock Planner", icon: RefreshCw },
    { id: "reviews", label: "Review Requests", icon: Mail },
    { id: "insights", label: "Seller Insights", icon: Lightbulb },
    { id: "settings", label: "Boutique Settings", icon: Settings },
  ];
  const filteredProducts = products.filter((product) => {
    const matchesSearch = `${product.name} ${product.brand} ${product.sku}`
      .toLowerCase()
      .includes(productSearch.toLowerCase());
    const matchesStatus = productStatusFilter === "All statuses" ||
      (product.status ?? "ACTIVE") === productStatusFilter.toUpperCase();
    return matchesSearch && matchesStatus &&
      (productCategory === "All categories" || product.category === productCategory);
  });
  const plan = dashboard?.selected_plan ?? seller.selected_plan ?? "boutique";
  const commissionRate = dashboard?.commission_rate ?? seller.commission_rate ?? 10;
  const salesSeries = dashboard?.sales_series ?? [];
  const periodGross = salesSeries.reduce((total, point) => total + point.gross, 0);
  const periodCommission = salesSeries.reduce((total, point) => total + point.commission, 0);
  const periodNet = salesSeries.reduce((total, point) => total + point.net, 0);
  const salesChartPeak = Math.max(1, ...salesSeries.map((point) => point.gross));

  return (
    <main className="seller-shell">
      <header className="seller-topbar">
        <button
          type="button"
          className="seller-mobile-menu"
          aria-label="Open seller navigation"
          aria-expanded={sidebarOpen}
          aria-controls="seller-portal-navigation"
          onClick={() => setSidebarOpen(true)}
        >
          <Menu size={19} />
        </button>
        <Link className="marketplace-brand" to="/">maison <span>muse.</span></Link>
        <div className="seller-topbar-actions">
          {demoMode && <span className="seller-demo-badge">DEMO PREVIEW · READ ONLY</span>}
          <span className={`seller-status-badge ${seller.status.toLowerCase()}`}>
            {demoMode ? "DEMO" : seller.status}
          </span>
          <button type="button" className="marketplace-button secondary" onClick={handleLogout}>
            {demoMode ? "Sign in / apply" : <><LogOut size={15} /> Sign out</>}
          </button>
        </div>
      </header>
      <div className="seller-layout">
        {sidebarOpen && (
          <button
            type="button"
            className="seller-mobile-scrim"
            aria-label="Close seller navigation"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <aside
          id="seller-portal-navigation"
          className={`seller-sidebar${sidebarOpen ? " is-open" : ""}`}
          aria-label="Seller portal navigation"
        >
          <div className="seller-sidebar-store">
            <span className="seller-store-avatar"><Store size={19} /></span>
            <div><strong>{seller.store_name}</strong><small>{seller.status === "APPROVED" ? "Seller Studio" : "Application"}</small></div>
          </div>
          <nav>
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                className={activeTab === id ? "active" : ""}
                onClick={() => {
                  setActiveTab(id);
                  setSidebarOpen(false);
                }}
              >
                <Icon size={17} /> <span>{label}</span>
              </button>
            ))}
          </nav>
          <Link className="seller-sidebar-link" to="/">← Back to storefront</Link>
        </aside>

        <div className="seller-workspace">
          <section className="seller-welcome">
            <div>
              <span className="marketplace-eyebrow">MAISON MUSE · SELLER STUDIO</span>
              <h1>Welcome, {seller.store_name}.</h1>
              <p>Manage your boutique, orders, and earnings in one place.</p>
            </div>
            {seller.status === "APPROVED" && !demoMode && (
              <Link className="marketplace-button secondary" to={`/boutiques/${encodeURIComponent(seller.store_slug)}`} target="_blank" rel="noreferrer">
                <Store size={15} /> View public store
              </Link>
            )}
          </section>
          {demoMode && (
            <div className="seller-demo-notice" role="status">
              This is sample seller data. Sign in or apply to sell to connect a real store and enable changes.
              <button type="button" onClick={() => openAccessForm("login")}>Sign in to your store <ArrowRight size={14} /></button>
            </div>
          )}
          {error && <p className="marketplace-error" role="alert">{error}</p>}
          {notice && <p className="marketplace-notice" role="status">{notice}</p>}

          {seller.status !== "APPROVED" ? (
            <section className="seller-pending-card">
              <span className="seller-pending-icon"><Store size={22} /></span>
              <div>
                <h2>{seller.status === "SUSPENDED" ? "Your store is paused" : "Your application is under review"}</h2>
                <p>{seller.status === "SUSPENDED" ? "Contact Maison Muse support for help restoring your seller access." : "We’ll review your business details. Product and order tools will unlock after approval."}</p>
                {seller.status === "PENDING" && seller.review_state !== "UNDER_AUDIT" && !demoMode && (
                  <button
                    type="button"
                    className="marketplace-button primary seller-approval-button"
                    disabled={saving}
                    onClick={unlockSellerStudio}
                  >
                    {saving ? "Unlocking…" : "Bypass Review & Unlock Seller Studio"}
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </section>
          ) : (
            <>
              {activeTab === "overview" && (
                <div className="seller-tab-content">
                  <SellerAdvancedTools tab="health" demoMode={demoMode} />
                  <section className="seller-analytics-toolbar">
                    <div><span className="marketplace-eyebrow">PERFORMANCE WINDOW</span><strong>Sales &amp; earnings</strong></div>
                    <label>Reporting period
                      <select value={analyticsPeriod} onChange={(event) => setAnalyticsPeriod(event.target.value)}>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                        <option value="ytd">Year-to-Date</option>
                      </select>
                    </label>
                  </section>
                  <section className="seller-metrics" aria-label="Store analytics">
                    {[
                      { label: "Gross sales · selected period", value: formatKsh(periodGross), icon: ChartNoAxesCombined },
                      { label: "Net earnings · selected period", value: formatKsh(periodNet), icon: CircleDollarSign },
                      { label: "Active inventory", value: dashboard?.product_count ?? products.length, icon: Package },
                      { label: "Pending orders", value: dashboard?.pending_orders ?? 0, icon: Box },
                      { label: "Average rating", value: `${Number(dashboard?.average_rating ?? seller.rating ?? 0).toFixed(1)} ★`, icon: Star },
                    ].map(({ label, value, icon: Icon }) => (
                      <article key={label}><span><Icon size={16} /></span><small>{label}</small><strong>{value}</strong></article>
                    ))}
                  </section>
                  <section className="seller-panel seller-sales-chart">
                    <header><div><span className="marketplace-eyebrow">REAL-TIME SALES</span><h2>Gross sales, fees &amp; net earnings</h2></div></header>
                    <div className="seller-chart-legend">
                      <span><i className="gross" /> Gross sales</span>
                      <span><i className="commission" /> Commission · {formatKsh(periodCommission)}</span>
                      <span><i className="net" /> Net · {formatKsh(periodNet)}</span>
                    </div>
                    <div className="seller-sales-bars" role="img" aria-label={`Sales breakdown for the selected ${analyticsPeriod} period`}>
                      {salesSeries.map((point) => (
                        <div className="seller-sales-day" key={point.date} title={`${point.date}: gross ${formatKsh(point.gross)}, commission ${formatKsh(point.commission)}, net ${formatKsh(point.net)}`}>
                          <time>{point.date.slice(5)}</time>
                          <div className="seller-sales-bar-track"><i className="gross" style={{ width: `${point.gross / salesChartPeak * 100}%` }} /></div>
                          <div className="seller-sales-bar-track"><i className="commission" style={{ width: `${point.commission / salesChartPeak * 100}%` }} /></div>
                          <div className="seller-sales-bar-track"><i className="net" style={{ width: `${point.net / salesChartPeak * 100}%` }} /></div>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section className="seller-fast-actions">
                    <div><span className="marketplace-eyebrow">FAST-ACTION COMMAND HUB</span><h2>Make your next move</h2></div>
                    <button type="button" className="marketplace-button primary" disabled={demoMode} onClick={() => setProductModal("new")}><Plus size={15} /> Quick Add Product</button>
                    <button type="button" className="marketplace-button secondary" onClick={() => setActiveTab("payouts")}><CircleDollarSign size={15} /> Request Instant M-Pesa Payout</button>
                    <button type="button" className="marketplace-button secondary" onClick={() => downloadMonthlyEarningsReport(seller, orders)}><Download size={15} /> Download Monthly Earnings Tax/VAT Invoice (CSV)</button>
                  </section>
                  <section className="seller-plan-bar">
                    <div><span className="marketplace-eyebrow">YOUR SELLER PLAN</span><strong>{PLAN_NAMES[plan] ?? PLAN_NAMES.boutique} — {commissionRate}% Fee</strong></div>
                    <button type="button" className="marketplace-button secondary" onClick={() => setActiveTab("settings")}>Compare plans <ArrowRight size={14} /></button>
                  </section>
                  <div className="seller-overview-grid">
                    <section className="seller-panel">
                      <header><div><span className="marketplace-eyebrow">RECENT ACTIVITY</span><h2>Recent sales</h2></div><button type="button" className="seller-inline-link" onClick={() => setActiveTab("orders")}>All orders</button></header>
                      {orders.length ? (
                        <div className="seller-table-wrap"><table className="seller-table">
                          <thead><tr><th>Order</th><th>Date</th><th>Status</th><th>Net payout</th></tr></thead>
                          <tbody>{orders.slice(0, 5).map((order) => (
                            <tr key={order.id}><td>{order.order_number}</td><td>{new Date(order.ordered_at).toLocaleDateString()}</td><td>{fulfillmentLabels[order.fulfillment_status] ?? order.fulfillment_status}</td><td>{formatKsh(order.seller_payout_amount)}</td></tr>
                          ))}</tbody>
                        </table></div>
                      ) : <p className="marketplace-empty">Your sales activity will appear here after your first order.</p>}
                    </section>
                    <section className="seller-panel">
                      <header><div><span className="marketplace-eyebrow">INVENTORY HEALTH</span><h2>Low-stock &amp; out-of-stock alerts</h2></div></header>
                      {products.filter((product) => product.stock <= (product.lowStockThreshold ?? product.low_stock_threshold ?? 5)).length ? (
                        <ul className="seller-low-stock-list">
                          {products.filter((product) => product.stock <= (product.lowStockThreshold ?? product.low_stock_threshold ?? 5)).slice(0, 5).map((product) => (
                            <li key={product.id}><span>{product.name}</span><strong>{product.stock === 0 ? "Out of stock" : `${product.stock} left`}</strong></li>
                          ))}
                        </ul>
                      ) : <p className="marketplace-empty">No low-stock products to flag.</p>}
                    </section>
                  </div>
                </div>
              )}

              {activeTab === "products" && (
                <div className="seller-tab-content">
                <section className="seller-panel">
                  <header className="seller-panel-heading">
                    <div><span className="marketplace-eyebrow">YOUR CATALOG</span><h2>Product inventory <small>{products.length} products</small></h2></div>
                    <button type="button" className="marketplace-button primary" disabled={demoMode} onClick={() => setProductModal("new")}><Plus size={16} /> Add product</button>
                  </header>
                  <p className="seller-operation-note">New listings start as drafts and remain hidden until an administrator approves their quality review. Open Quality Control to track or resubmit them.</p>
                  <div className="seller-filters">
                    <label className="seller-search"><Search size={16} /><input aria-label="Search products" placeholder="Search name, brand, or SKU" value={productSearch} onChange={(event) => setProductSearch(event.target.value)} /></label>
                    <select aria-label="Filter products by category" value={productCategory} onChange={(event) => setProductCategory(event.target.value)}>
                      <option>All categories</option>{categories.map((category) => <option key={category}>{category}</option>)}
                    </select>
                    <select aria-label="Filter products by status" value={productStatusFilter} onChange={(event) => setProductStatusFilter(event.target.value)}>
                      <option>All statuses</option><option value="Active">Active</option><option value="Draft">Draft</option><option value="Archived">Archived</option>
                    </select>
                  </div>
                  <div className="seller-bulk-toolbar">
                    <label className="seller-select-all"><input
                      type="checkbox"
                      checked={filteredProducts.length > 0 && filteredProducts.every((product) => selectedProductIds.includes(product.id))}
                      onChange={(event) => setSelectedProductIds(event.target.checked ? filteredProducts.map((product) => product.id) : [])}
                    /> Select visible ({selectedProductIds.length} selected)</label>
                    <select aria-label="Bulk product status" value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value)}>
                      <option value="ACTIVE">Active</option><option value="DRAFT">Draft</option><option value="ARCHIVED">Archived</option>
                    </select>
                    <button type="button" className="marketplace-button secondary" disabled={!selectedProductIds.length || saving || demoMode} onClick={() => applyBulkAction("status", bulkStatus)}>Apply status</button>
                    <button type="button" className="marketplace-button secondary" disabled={!selectedProductIds.length || saving || demoMode} onClick={() => applyBulkAction("out_of_stock")}>Mark out of stock</button>
                    <label className="seller-discount-field">Discount
                      <input type="number" min="1" max="90" value={bulkDiscount} onChange={(event) => setBulkDiscount(event.target.value)} /> %
                    </label>
                    <button type="button" className="marketplace-button secondary" disabled={!selectedProductIds.length || saving || demoMode} onClick={() => applyBulkAction("discount", bulkDiscount)}>Apply discount</button>
                  </div>
                  {filteredProducts.length ? (
                    <div className="seller-product-list">
                      {filteredProducts.map((product) => (
                        <article key={product.id}>
                          <input
                            type="checkbox"
                            aria-label={`Select ${product.name}`}
                            checked={selectedProductIds.includes(product.id)}
                            onChange={(event) => setSelectedProductIds((current) =>
                              event.target.checked
                                ? [...current, product.id]
                                : current.filter((id) => id !== product.id),
                            )}
                          />
                          <ProductImage src={product.image} alt="" />
                          <div><strong>{product.name}</strong><small>{product.category} · {product.sku} · {formatKsh(product.price)} · {product.stock} in stock · {product.status ?? "ACTIVE"}{product.qc_status ? ` · ${product.qc_status.replaceAll("_", " ")}` : ""}</small><span className={`seller-stock-badge ${product.stock <= 0 ? "sold-out" : product.stock < 5 ? "low-stock" : "in-stock"}`}>{product.stock <= 0 ? "Sold Out" : product.stock < 5 ? "Low Stock" : "In Stock"}</span></div>
                          <button type="button" onClick={() => setProductPreview(product)}>Preview on Storefront</button>
                          <button type="button" disabled={demoMode} aria-label={`Edit ${product.name}`} onClick={() => setProductModal(product)}>Edit</button>
                          <button type="button" className="seller-delete-button" disabled={demoMode} aria-label={`Remove ${product.name}`} onClick={() => removeProduct(product)}><Trash2 size={16} /></button>
                        </article>
                      ))}
                    </div>
                  ) : <p className="marketplace-empty">No products match your search. Add your first product to start your catalog.</p>}
                </section>
                <BulkProductManager
                  demoMode={demoMode}
                  onNotice={setNotice}
                  onImported={async () => {
                    setProducts(await fetchSellerProducts());
                    setDashboard(await fetchSellerDashboard(analyticsPeriod));
                  }}
                />
                </div>
              )}

              {activeTab === "orders" && <OrderFulfillment readOnly={demoMode} />}

              {activeTab === "payouts" && (
                <div className="seller-tab-content">
                  <div className="seller-fee-breakdown">
                    <span>Paid gross sales <strong>{formatKsh(dashboard?.gross_sales ?? 0)}</strong></span>
                    <span>− Platform commission ({commissionRate}%) <strong>{formatKsh((dashboard?.gross_sales ?? 0) - (dashboard?.net_earnings ?? 0))}</strong></span>
                    <span>= Net seller earnings (including escrow) <strong>{formatKsh(dashboard?.net_earnings ?? 0)}</strong></span>
                  </div>
                  <section className="seller-payout-summary">
                    <div>
                      <span className="marketplace-eyebrow">AVAILABLE BALANCE</span>
                      <strong>{formatKsh(dashboard?.available_balance ?? 0)}</strong>
                      <small>Paid and delivered orders not yet allocated to a payout.</small>
                      {(dashboard?.pending_delivery_balance ?? 0) > 0 && (
                        <p className="seller-pending-escrow">
                          {formatKsh(dashboard.pending_delivery_balance)} is held in escrow until the orders are marked delivered. Check Order Fulfillment after delivery.
                        </p>
                      )}
                    </div>
                    <div className="seller-payout-action">
                      <span className="seller-demo-badge">SIMULATION ONLY · NO REAL TRANSFER</span>
                      <div className="seller-withdrawal-fields">
                        <label>Amount (KSh · demo minimum 1)
                          <input type="number" min="1" step="0.01" max={dashboard?.available_balance ?? 0} value={payoutForm.amount} onChange={(event) => setPayoutForm((current) => ({ ...current, amount: event.target.value }))} />
                        </label>
                        <label>Destination
                          <select value={payoutForm.destination_type} onChange={(event) => setPayoutForm((current) => ({ ...current, destination_type: event.target.value, destination: "" }))}>
                            <option value="registered_phone">Registered M-Pesa destination</option>
                            <option value="paybill">Paybill</option>
                            <option value="till">Till number</option>
                          </select>
                        </label>
                        {payoutForm.destination_type !== "registered_phone" && (
                          <label>{payoutForm.destination_type === "paybill" ? "Paybill number" : "Till number"}
                            <input required value={payoutForm.destination} onChange={(event) => setPayoutForm((current) => ({ ...current, destination: event.target.value }))} />
                          </label>
                        )}
                        <div className="seller-payout-buttons">
                          <button type="button" className="marketplace-button primary" disabled={demoMode || saving || (dashboard?.available_balance ?? 0) < 1 || seller.payout_method !== "M-Pesa" || (payoutForm.destination_type !== "registered_phone" && !payoutForm.destination.trim())} onClick={() => requestDemoPayout(dashboard?.available_balance ?? 0)}>
                            {saving ? "Processing…" : "Withdraw available balance (Demo)"}
                          </button>
                          <button type="button" className="marketplace-button secondary" disabled={demoMode || saving || Number(payoutForm.amount) < 1 || Number(payoutForm.amount) > (dashboard?.available_balance ?? 0) || seller.payout_method !== "M-Pesa" || (payoutForm.destination_type !== "registered_phone" && !payoutForm.destination.trim())} onClick={() => requestDemoPayout()}>
                            {saving ? "Processing…" : "Request a partial demo payout"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </section>
                  <section className="seller-panel">
                    <header>
                      <div><span className="marketplace-eyebrow">PAYOUT HISTORY</span><h2>Financial ledger</h2></div>
                      <button type="button" className="marketplace-button secondary" onClick={() => downloadCsv(
                        "maison-muse-payout-statement.csv",
                        [
                          ["Date", "Transaction reference", "Gross KSh", "Commission KSh", "Net paid KSh", "Destination", "Status"],
                          ...payouts.map((payout) => [payout.date, payout.transaction_id || payout.reference, payout.gross_amount, payout.commission_retained, payout.net_paid, `${payout.destination_type ?? ""} ${payout.destination_hint ?? ""}`, payout.status]),
                        ],
                      )}><Download size={15} /> Download CSV statement</button>
                    </header>
                    {payouts.length ? <div className="seller-table-wrap"><table className="seller-table">
                      <thead><tr><th>Date</th><th>Transaction ref</th><th>Gross</th><th>Net paid</th><th>Channel</th><th>Status</th></tr></thead>
                      <tbody>{payouts.map((payout) => (
                        <tr key={payout.id}><td>{new Date(payout.date).toLocaleDateString()}</td><td>{payout.transaction_id || payout.reference}{payout.is_demo && <small className="seller-ledger-demo">Demo</small>}</td><td>{formatKsh(payout.gross_amount)}</td><td>{formatKsh(payout.net_paid)}</td><td>{payout.payout_method}</td><td>{payout.status}</td></tr>
                      ))}</tbody>
                    </table></div> : <p className="marketplace-empty">Payout transactions will appear here.</p>}
                  </section>
                </div>
              )}

              {activeTab === "settings" && settingsForm && (
                <div className="seller-tab-content">
                  <section className="seller-panel">
                    <header><div><span className="marketplace-eyebrow">BOUTIQUE BRANDING</span><h2>Storefront settings</h2></div></header>
                    <form className="marketplace-form-grid" onSubmit={saveStorefrontSettings}>
                      <label>Store name<input required minLength="2" disabled={demoMode} value={settingsForm.store_name} onChange={(event) => setSettingsForm((current) => ({ ...current, store_name: event.target.value }))} /></label>
                      <label>Primary category<select disabled={demoMode} value={settingsForm.business_category} onChange={(event) => setSettingsForm((current) => ({ ...current, business_category: event.target.value }))}>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
                      <label className="marketplace-form-wide">Store bio<textarea rows="4" maxLength="1000" disabled={demoMode} value={settingsForm.store_bio} onChange={(event) => setSettingsForm((current) => ({ ...current, store_bio: event.target.value }))} /></label>
                      <label>Choose a store logo from your computer or phone (JPEG, PNG, WebP · 5 MB max)<input type="file" accept="image/jpeg,image/png,image/webp" disabled={demoMode || saving} onChange={(event) => { void uploadStoreAsset("logo_url", event.target.files?.[0]); event.target.value = ""; }} /></label>
                      <label>Choose a cover photo from your computer or phone (JPEG, PNG, WebP · 5 MB max)<input type="file" accept="image/jpeg,image/png,image/webp" disabled={demoMode || saving} onChange={(event) => { void uploadStoreAsset("banner_url", event.target.files?.[0]); event.target.value = ""; }} /></label>
                      <label className="marketplace-form-wide">Logo URL<input type="url" disabled={demoMode} value={settingsForm.logo_url} onChange={(event) => setSettingsForm((current) => ({ ...current, logo_url: event.target.value }))} /></label>
                      <label className="marketplace-form-wide">Cover banner URL<input type="url" disabled={demoMode} value={settingsForm.banner_url} onChange={(event) => setSettingsForm((current) => ({ ...current, banner_url: event.target.value }))} /></label>
                      <label>Business email<input type="email" required disabled={demoMode} value={settingsForm.business_email ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, business_email: event.target.value }))} /></label>
                      <label>Business phone<input type="tel" required disabled={demoMode} value={settingsForm.business_phone} onChange={(event) => setSettingsForm((current) => ({ ...current, business_phone: event.target.value }))} /></label>
                      <label>WhatsApp support number<input type="tel" disabled={demoMode} value={settingsForm.whatsapp_phone} onChange={(event) => setSettingsForm((current) => ({ ...current, whatsapp_phone: event.target.value }))} /></label>
                      <label>Instagram business URL<input type="url" disabled={demoMode} value={settingsForm.instagram_url} onChange={(event) => setSettingsForm((current) => ({ ...current, instagram_url: event.target.value }))} /></label>
                      <label>TikTok business URL<input type="url" disabled={demoMode} value={settingsForm.tiktok_url} onChange={(event) => setSettingsForm((current) => ({ ...current, tiktok_url: event.target.value }))} /></label>
                      <label className="marketplace-form-wide">Operating hours<textarea rows="2" maxLength="1000" disabled={demoMode} value={settingsForm.operating_hours} onChange={(event) => setSettingsForm((current) => ({ ...current, operating_hours: event.target.value }))} placeholder="Mon–Fri, 9:00–18:00" /></label>
                      <label className="seller-holiday-toggle"><input type="checkbox" disabled={demoMode} checked={settingsForm.holiday_mode} onChange={(event) => setSettingsForm((current) => ({ ...current, holiday_mode: event.target.checked }))} /> Holiday mode — pause new orders while keeping products visible</label>
                      <label>Payout channel<select disabled={demoMode} value={settingsForm.payout_method} onChange={(event) => setSettingsForm((current) => ({ ...current, payout_method: event.target.value }))}><option>M-Pesa</option><option>Bank</option></select></label>
                      <label className="marketplace-form-wide">{settingsForm.payout_method === "M-Pesa" ? "Registered M-Pesa phone (verified)" : "Bank account details"}<input required disabled={demoMode || settingsForm.payout_method === "M-Pesa"} value={settingsForm.payout_method === "M-Pesa" ? settingsForm.business_phone : settingsForm.payout_account} onChange={(event) => setSettingsForm((current) => ({ ...current, payout_account: event.target.value }))} /></label>
                      <div className="marketplace-form-wide seller-form-actions"><button type="submit" className="marketplace-button primary" disabled={demoMode || saving}>{saving ? "Saving…" : "Save storefront settings"}</button></div>
                    </form>
                  </section>
                  {profileVerificationPending && (
                    <section className="seller-panel seller-verification-panel">
                      <span className="marketplace-eyebrow">CONTACT SECURITY</span>
                      <h2>Confirm your email or phone change</h2>
                      <p>Enter the 6-digit code sent to your email address. It expires in 10 minutes.</p>
                      <form className="seller-advanced-form" onSubmit={confirmSellerProfileUpdate}>
                        <label>Confirmation code<input required inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={profileVerificationCode} onChange={(event) => setProfileVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
                        <button className="marketplace-button primary" type="submit" disabled={demoMode || saving || profileVerificationCode.length !== 6}>{saving ? "Verifying…" : "Verify and save changes"}</button>
                      </form>
                    </section>
                  )}
                  <SellerNotificationSettings demoMode={demoMode} />
                </div>
              )}
              {activeTab === "subscription" && (
                <section className="seller-panel seller-tab-content seller-plan-options">
                  <span className="marketplace-eyebrow">SELLER PLANS · SIMULATED M-PESA STK</span>
                  <h2>Subscription &amp; membership</h2>
                  <p>Plan changes update commission on future orders. Payment references are demonstrations only; no charge is made.</p>
                  <div className="seller-plan-cards">
                    {[
                      { id: "boutique", name: "Boutique Starter", price: "Free", fee: "10% commission", details: "Up to 15 listings · standard payouts" },
                      { id: "pro", name: "Pro Beauty Studio", price: "KSh 2,500 / month", fee: "5% commission", details: "Unlimited listings · priority search · daily payouts" },
                      { id: "enterprise", name: "Enterprise Brand", price: "KSh 7,500 / month", fee: "2.5% commission", details: "Account manager · API sync · featured placement" },
                    ].map((option) => (
                      <label className={`seller-plan-choice ${plan === option.id ? "current" : ""} ${planSelection === option.id ? "selected" : ""}`} key={option.id}>
                        <input type="radio" name="seller-plan" value={option.id} checked={planSelection === option.id} onChange={() => setPlanSelection(option.id)} disabled={demoMode || saving} />
                        <strong>{option.name}{plan === option.id ? " · Current" : ""}</strong>
                        <span>{option.price} · {option.fee}</span>
                        <small>{option.details}</small>
                      </label>
                    ))}
                  </div>
                  <button type="button" className="marketplace-button primary" disabled={demoMode || saving || planSelection === plan} onClick={savePlanSelection}>
                    {saving ? "Sending simulated STK push…" : planSelection === plan ? "Current plan selected" : `Pay & activate ${PLAN_NAMES[planSelection]}`}
                  </button>
                </section>
              )}
              {["promotions", "sponsored", "returns"].includes(activeTab) && (
                <SellerAdvancedTools tab={activeTab} products={products} demoMode={demoMode} onNotice={setNotice} />
              )}
              {[
                "team",
                "messages",
                "logistics",
                "quality",
                "statement",
                "repricing",
                "branches",
                "restock",
                "reviews",
                "insights",
              ].includes(activeTab) && (
                <SellerOperations
                  tab={activeTab}
                  products={products}
                  orders={orders}
                  demoMode={demoMode}
                  onNotice={setNotice}
                />
              )}
            </>
          )}
        </div>
      </div>
      {productModal && !demoMode && <ProductEditor product={productModal === "new" ? null : productModal} onClose={() => setProductModal(null)} onSave={saveProduct} onUploadImage={uploadProductImage} saving={saving} />}
      {productPreview && (
        <div className="marketplace-modal-backdrop" onMouseDown={() => setProductPreview(null)}>
          <section className="marketplace-modal seller-product-preview" role="dialog" aria-modal="true" aria-labelledby="seller-preview-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span className="marketplace-eyebrow">BUYER STOREFRONT PREVIEW</span><h2 id="seller-preview-title">Preview on Storefront</h2></div>
              <button type="button" className="marketplace-icon-button" aria-label="Close preview" onClick={() => setProductPreview(null)}><X size={18} /></button>
            </header>
            <article className="seller-preview-product">
              <ProductImage src={productPreview.image} alt={productPreview.name} />
              <span className="marketplace-eyebrow">{productPreview.category}</span>
              <h3>{productPreview.name}</h3>
              <p>{productPreview.detail}</p>
              <strong>{formatKsh(productPreview.price)}</strong>
              <span className="product-seller-attribution">Sold &amp; fulfilled by {seller.store_name} <Store size={13} /></span>
              <small>{productPreview.stock > 0 ? `${productPreview.stock} available` : "Sold out"} · {productPreview.status ?? "ACTIVE"}</small>
            </article>
            <footer>
              <button type="button" className="marketplace-button secondary" onClick={() => setProductPreview(null)}>Close preview</button>
              <Link className="marketplace-button primary" to={`/boutiques/${encodeURIComponent(seller.store_slug)}`} target="_blank" rel="noreferrer">View public boutique <ArrowRight size={14} /></Link>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}

export default SellerDashboard;
