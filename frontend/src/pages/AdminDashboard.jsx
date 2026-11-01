import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { App as CapacitorApp } from "@capacitor/app";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Box,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  CreditCard,
  ExternalLink,
  Eye,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Pencil,
  Plus,
  Search,
  Settings,
  Shield,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Store,
  ClipboardList,
  ReceiptText,
  UserSearch,
  Warehouse,
  Trash2,
  Truck,
  Users,
  X,
  Copy,
  Pause,
  HandCoins,
  BarChart3,
  PackageSearch,
  MessageCircle,
} from "lucide-react";
import { formatKsh } from "../data/currency.js";
import { PRODUCT_CATEGORIES } from "../data/products.js";
import useAndroidBackButton from "../hooks/useAndroidBackButton.js";
import {
  adminLogin,
  adminLogout,
  createAdminCampaign,
  createAdminProduct,
  deactivateAdminCampaign,
  deleteAdminProduct,
  duplicateAdminProduct,
  fetchAdminCampaigns,
  fetchAdminCustomers,
  fetchAdminNotifications,
  fetchAdminOrder,
  fetchAdminOrders,
  fetchAdminOverview,
  fetchAdminProducts,
  fetchAdminSellerQc,
  fetchAdminSettings,
  getAdminSession,
  updateAdminOrderStatus,
  updateAdminProduct,
  updateAdminProductStock,
  updateAdminSettings,
  decideAdminSellerQc,
} from "../services/api.js";
import SecurityManager from "../admin/components/SecurityManager.jsx";
import AuditLogs from "../admin/components/AuditLogs.jsx";
import PaymentLogs from "../admin/components/PaymentLogs.jsx";
import CustomerInsights from "../admin/components/CustomerInsights.jsx";
import SupplierManager from "../admin/components/SupplierManager.jsx";
import VendorManager from "../admin/components/VendorManager.jsx";
import CommissionManager from "../admin/components/CommissionManager.jsx";
import AdminOrders from "../admin/AdminOrders.jsx";
import AnalyticsOverview from "../admin/components/AnalyticsOverview.jsx";
import AdminSupport from "../admin/AdminSupport.jsx";
import "./AdminDashboard.css";

const ORDER_FILTERS = [
  "all",
  "pending",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
];
const NAV_ITEMS = [
  { id: "overview", label: "Dashboard analytics", icon: LayoutDashboard },
  { id: "products", label: "Product management", icon: Package },
  { id: "sellerQc", label: "Seller catalog QC", icon: ShieldCheck },
  { id: "orders", label: "Order fulfillment", icon: ShoppingBag },
  { id: "inventory", label: "Inventory control", icon: Box },
  { id: "customers", label: "Customer directory", icon: Users },
  { id: "campaigns", label: "Flash sale & promos", icon: Sparkles },
  { id: "settings", label: "System settings", icon: Settings },
  { id: "security", label: "Security & access", icon: Shield },
  { id: "audit", label: "System audit logs", icon: ClipboardList },
  { id: "payments", label: "Payment reconciliation", icon: ReceiptText },
  { id: "insights", label: "Customer insights", icon: UserSearch },
  { id: "suppliers", label: "Suppliers & COGS", icon: Warehouse },
  { id: "vendors", label: "Marketplace vendors", icon: Store },
  { id: "commissions", label: "Commissions & payouts", icon: HandCoins },
  { id: "marketplaceOrders", label: "Marketplace orders", icon: PackageSearch },
  { id: "marketplaceAnalytics", label: "Marketplace analytics", icon: BarChart3 },
  { id: "support", label: "Customer support", icon: MessageCircle },
];
const NAV_ACCESS = {
  overview: ["analytics", "read"],
  products: ["products", "read"],
  sellerQc: ["products", "read"],
  orders: ["orders", "read"],
  inventory: ["products", "read"],
  customers: ["orders", "read"],
  campaigns: ["settings", "read"],
  settings: ["settings", "read"],
  security: ["settings", "read"],
  audit: ["settings", "read"],
  payments: ["orders", "read"],
  insights: ["orders", "read"],
  suppliers: ["products", "read"],
  vendors: ["settings", "write"],
  commissions: ["settings", "write"],
  marketplaceOrders: ["orders", "read"],
  marketplaceAnalytics: ["analytics", "read"],
  support: ["support", "read"],
};
const CATEGORY_DETAIL_FIELDS = {
  "Perfumes & Fragrances": [
    ["scentNotes", "Scent notes"],
    ["wearTime", "Wear time"],
    ["volume", "Volume"],
    ["concentration", "Concentration"],
  ],
  "Press-On Nails": [
    ["shape", "Nail shape"],
    ["finish", "Finish"],
    ["wearTime", "Wear time"],
    ["availableSizes", "Sizes (comma separated)"],
  ],
  "Skincare & Glow": [
    ["keyIngredients", "Key ingredients"],
    ["volume", "Volume"],
    ["skinType", "Skin type"],
    ["howToUse", "How to use"],
  ],
  "Lip & Makeup Essentials": [
    ["shade", "Shade"],
    ["finish", "Finish"],
    ["wearTime", "Wear time"],
    ["volume", "Volume"],
  ],
  "Hair & Accessories": [
    ["material", "Material"],
    ["setIncludes", "Set includes"],
    ["care", "Care instructions"],
    ["color", "Color"],
  ],
};
const DEFAULT_TAG_COLORS = {
  "BEST SELLER": "bg-rose-600",
  "FLASH DEAL": "bg-[#e61601]",
  "VIRAL PICK": "bg-purple-600",
  "CLEAN BEAUTY": "bg-emerald-600",
};
const emptyProduct = {
  name: "",
  brand: "Maison Muse",
  sku: "",
  category: PRODUCT_CATEGORIES[0],
  detail: "",
  description: "",
  price: "",
  unitCost: "",
  oldPrice: "",
  stock: "12",
  lowStockThreshold: "5",
  tag: "BEST SELLER",
  images: "",
  details: {},
};

function readPreference(key, fallback) {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function stockState(product) {
  if (product.stock <= 0) return { label: "Out of stock", className: "out" };
  if (product.stock <= (product.lowStockThreshold ?? 5)) {
    return { label: "Low stock", className: "low" };
  }
  return { label: "In stock", className: "in" };
}

function statusLabel(status) {
  return status.replaceAll("_", " ");
}

function RevenueChart({ points, period }) {
  const width = 760;
  const height = 220;
  const padding = { top: 18, right: 12, bottom: 32, left: 12 };
  const max = Math.max(...points.map((point) => point.revenue), 1);
  const maxOrders = Math.max(...points.map((point) => point.orders), 1);
  const coordinates = points.map((point, index) => ({
    ...point,
    x:
      padding.left +
      (index * (width - padding.left - padding.right)) /
        Math.max(1, points.length - 1),
    y:
      padding.top +
      (height - padding.top - padding.bottom) * (1 - point.revenue / max),
    orderY:
      padding.top +
      (height - padding.top - padding.bottom) * (1 - point.orders / maxOrders),
  }));
  const line = coordinates.map((point) => `${point.x},${point.y}`).join(" ");
  const orderLine = coordinates
    .map((point) => `${point.x},${point.orderY}`)
    .join(" ");
  const area = `${padding.left},${height - padding.bottom} ${line} ${
    width - padding.right
  },${height - padding.bottom}`;

  return (
    <div className="admin-chart-wrap">
      <svg
        className="admin-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${period} revenue and sales trend`}
      >
        {[0, 1, 2, 3].map((lineIndex) => {
          const y =
            padding.top +
            (lineIndex * (height - padding.top - padding.bottom)) / 3;
          return (
            <line
              key={lineIndex}
              x1={padding.left}
              x2={width - padding.right}
              y1={y}
              y2={y}
              className="admin-chart-gridline"
            />
          );
        })}
        <polygon points={area} className="admin-chart-area" />
        <polyline points={line} className="admin-chart-line" />
        <polyline points={orderLine} className="admin-chart-order-line" />
        {coordinates.map((point) => (
          <g key={`${point.label}-${point.x}`}>
            <circle cx={point.x} cy={point.y} r="4" className="admin-chart-point" />
            <circle cx={point.x} cy={point.orderY} r="3" className="admin-chart-order-point" />
            <text
              x={point.x}
              y={height - 8}
              textAnchor="middle"
              className="admin-chart-label"
            >
              {point.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function CampaignCountdown({ endsAt }) {
  const getRemaining = () =>
    Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000));
  const [remaining, setRemaining] = useState(getRemaining);

  useEffect(() => {
    const timer = window.setInterval(() => setRemaining(getRemaining()), 1000);
    return () => window.clearInterval(timer);
  }, [endsAt]);

  if (!remaining) return <span><Clock3 size={14} />Campaign ended</span>;
  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  const countdown = days
    ? `${days}d ${String(hours).padStart(2, "0")}h`
    : `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return <span><Clock3 size={14} />Ends in {countdown}</span>;
}

function ProductModal({ product, onClose, onSave, saving }) {
  const [form, setForm] = useState(() => {
    if (!product) return emptyProduct;
    return {
      ...product,
      price: String(product.price),
      oldPrice: product.oldPrice ? String(product.oldPrice) : "",
      unitCost: String(product.unitCost ?? 0),
      stock: String(product.stock),
      lowStockThreshold: String(product.lowStockThreshold ?? 5),
      images: (product.images ?? product.gallery ?? [product.image]).join("\n"),
      details: product.details ?? {},
    };
  });
  const [error, setError] = useState("");
  const detailFields = CATEGORY_DETAIL_FIELDS[form.category] ?? [];
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    const images = form.images
      .split(/\r?\n/)
      .map((image) => image.trim())
      .filter(Boolean);
    if (!images.length || images.some((image) => !image.startsWith("https://"))) {
      setError("Enter at least one valid HTTPS image URL.");
      return;
    }
    const details = Object.fromEntries(
      detailFields
        .map(([key]) => [
          key,
          key === "availableSizes"
            ? String(form.details[key] ?? "XS, S, M, L")
                .split(",")
                .map((size) => size.trim())
                .filter(Boolean)
            : String(form.details[key] ?? "").trim(),
        ])
        .filter(([, value]) => (Array.isArray(value) ? value.length : value)),
    );
    try {
      await onSave({
        name: form.name,
        brand: form.brand,
        sku: form.sku,
        category: form.category,
        detail: form.detail,
        description: form.description,
        price: Number(form.price),
        unitCost: Number(form.unitCost || 0),
        oldPrice: form.oldPrice ? Number(form.oldPrice) : null,
        stock: Number(form.stock),
        lowStockThreshold: Number(form.lowStockThreshold),
        rating: Number(form.rating ?? 0),
        reviewsCount: Number(form.reviewsCount ?? 0),
        tag: form.tag,
        tagColor: DEFAULT_TAG_COLORS[form.tag],
        images,
        details,
        active: true,
      });
    } catch (saveError) {
      setError(saveError.message);
    }
  };

  return (
    <div className="admin-modal-backdrop" onMouseDown={onClose}>
      <section
        className="admin-modal admin-product-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-form-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="admin-modal-header">
          <div>
            <span className="admin-overline">CATALOG STUDIO</span>
            <h2 id="product-form-title">{product ? "Edit product" : "Add a product"}</h2>
          </div>
          <button type="button" className="admin-icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <form className="admin-product-form" onSubmit={submit}>
          <div className="admin-product-form-grid">
            <label>
              Product name
              <input required minLength={2} value={form.name} onChange={(e) => update("name", e.target.value)} />
            </label>
            <label>
              Brand
              <input required value={form.brand} onChange={(e) => update("brand", e.target.value)} />
            </label>
            <label>
              Category
              <select value={form.category} onChange={(e) => update("category", e.target.value)}>
                {PRODUCT_CATEGORIES.map((category) => <option key={category}>{category}</option>)}
              </select>
            </label>
            <label>
              SKU
              <input required pattern="[A-Za-z0-9._-]+" value={form.sku} onChange={(e) => update("sku", e.target.value)} />
            </label>
            <label className="admin-form-wide">
              Short description
              <input required minLength={5} value={form.detail} onChange={(e) => update("detail", e.target.value)} />
            </label>
            <label className="admin-form-wide">
              Long description
              <textarea required minLength={10} rows="3" value={form.description} onChange={(e) => update("description", e.target.value)} />
            </label>
            <label>
              Selling price (KSh)
              <input type="number" min="1" step="1" required value={form.price} onChange={(e) => update("price", e.target.value)} />
            </label>
            <label>
              Unit cost (KSh)
              <input type="number" min="0" step="1" value={form.unitCost} onChange={(e) => update("unitCost", e.target.value)} />
            </label>
            <label>
              Original price (KSh)
              <input type="number" min="1" step="1" value={form.oldPrice} onChange={(e) => update("oldPrice", e.target.value)} />
            </label>
            <label>
              Stock quantity
              <input type="number" min="0" step="1" required value={form.stock} onChange={(e) => update("stock", e.target.value)} />
            </label>
            <label>
              Low-stock alert at
              <input type="number" min="0" step="1" required value={form.lowStockThreshold} onChange={(e) => update("lowStockThreshold", e.target.value)} />
            </label>
            <label>
              Promotional badge
              <select value={form.tag} onChange={(e) => update("tag", e.target.value)}>
                {Object.keys(DEFAULT_TAG_COLORS).map((tag) => <option key={tag}>{tag}</option>)}
              </select>
            </label>
            <label>
              Rating (0–5)
              <input type="number" min="0" max="5" step="0.1" value={form.rating ?? 0} onChange={(e) => update("rating", e.target.value)} />
            </label>
            {detailFields.map(([key, label]) => (
              <label key={key} className={key === "howToUse" ? "admin-form-wide" : ""}>
                {label}
                <input
                  value={
                    Array.isArray(form.details[key])
                      ? form.details[key].join(", ")
                      : form.details[key] ?? ""
                  }
                  placeholder={key === "availableSizes" ? "XS, S, M, L" : ""}
                  onChange={(e) =>
                    setForm((current) => ({
                      ...current,
                      details: { ...current.details, [key]: e.target.value },
                    }))
                  }
                />
              </label>
            ))}
            <label className="admin-form-wide">
              Product image URLs (one HTTPS URL per line)
              <textarea required rows="3" value={form.images} onChange={(e) => update("images", e.target.value)} />
            </label>
          </div>
          {form.images.trim().startsWith("https://") && (
            <div className="admin-media-preview">
              <img src={form.images.trim().split(/\r?\n/)[0]} alt="Product image preview" />
              <span>Image preview</span>
            </div>
          )}
          {error && <p className="admin-inline-error" role="alert">{error}</p>}
          <footer className="admin-modal-actions">
            <button type="button" className="admin-button secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="admin-button primary" disabled={saving}>
              {saving ? "Saving…" : product ? "Save changes" : "Create product"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function OrderModal({ order, onClose, onStatusChange, saving, canUpdate }) {
  if (!order) return null;
  return (
    <div className="admin-modal-backdrop" onMouseDown={onClose}>
      <section className="admin-modal admin-order-modal" role="dialog" aria-modal="true" aria-labelledby="order-modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="admin-modal-header">
          <div>
            <span className="admin-overline">ORDER FULFILLMENT</span>
            <h2 id="order-modal-title">{order.order_number}</h2>
          </div>
          <button type="button" className="admin-icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="admin-order-detail-grid">
          <div className="admin-detail-card">
            <h3>Customer & delivery</h3>
            <strong>{order.customer.name}</strong>
            <a href={`tel:${order.customer.phone}`}>{order.customer.phone}</a>
            <p>{order.customer.address}</p>
            <span>Placed {formatDate(order.created_at)}</span>
          </div>
          <div className="admin-detail-card">
            <h3>Payment</h3>
            <strong>{order.payment_method === "pesapal" ? "Pesapal" : order.payment_method === "mobile-money" ? "M-Pesa / Mobile Money" : order.payment_method === "card" ? "Card" : "Cash on Delivery"}</strong>
            <span className={`admin-status ${order.payment_status === "paid" ? "in" : "pending"}`}>{statusLabel(order.payment_status)}</span>
          </div>
        </div>
        <div className="admin-order-line-items">
          <h3>Items in this order</h3>
          {(order.items ?? []).map((item) => (
            <div className="admin-order-line" key={`${item.product_id}-${item.variant}`}>
              <span><strong>{item.name}</strong><small>{item.variant ? `Size ${item.variant} · ` : ""}{item.quantity} × {formatKsh(item.price)}</small></span>
              <strong>{formatKsh(item.line_total)}</strong>
            </div>
          ))}
        </div>
        <div className="admin-order-totals">
          <span>Subtotal <strong>{formatKsh(order.subtotal)}</strong></span>
          <span>Shipping <strong>{order.shipping ? formatKsh(order.shipping) : "Complimentary"}</strong></span>
          <span>Tax <strong>{formatKsh(order.tax)}</strong></span>
          <span>Total <strong>{formatKsh(order.total)}</strong></span>
        </div>
        <label className="admin-status-update">
          Fulfillment status
          <select value={order.status} disabled={saving || !canUpdate} onChange={(event) => onStatusChange(order.order_number, event.target.value)}>
            {ORDER_FILTERS.filter((value) => value !== "all").map((value) => <option value={value} key={value}>{statusLabel(value)}</option>)}
          </select>
        </label>
      </section>
    </div>
  );
}

function AdminDashboard() {
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [loginError, setLoginError] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(() => {
    if (window.location.pathname.replace(/\/+$/, "").endsWith("/admin/support")) {
      return "support";
    }
    const requestedPage = new URLSearchParams(window.location.search).get("section");
    if (NAV_ITEMS.some((item) => item.id === requestedPage)) return requestedPage;
    const savedPage = readPreference("mm-admin-page", "overview");
    return NAV_ITEMS.some((item) => item.id === savedPage) ? savedPage : "overview";
  });
  const [period, setPeriod] = useState(() => {
    const savedPeriod = readPreference("mm-admin-period", "weekly");
    return ["daily", "weekly", "monthly"].includes(savedPeriod)
      ? savedPeriod
      : "weekly";
  });
  const [query, setQuery] = useState("");
  const [orderFilter, setOrderFilter] = useState("all");
  const [overview, setOverview] = useState(null);
  const [products, setProducts] = useState([]);
  const [sellerQc, setSellerQc] = useState([]);
  const [orders, setOrders] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [notifications, setNotifications] = useState({ low_stock: [], new_orders: [] });
  const [campaigns, setCampaigns] = useState([]);
  const [settings, setSettings] = useState(null);
  const [pageError, setPageError] = useState("");
  const [toast, setToast] = useState("");
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [productModal, setProductModal] = useState(null);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const handleAndroidBackButton = useCallback(({ canGoBack }) => {
    if (selectedOrder) {
      setSelectedOrder(null);
    } else if (productModal) {
      setProductModal(null);
    } else if (notificationOpen) {
      setNotificationOpen(false);
    } else if (sidebarOpen) {
      setSidebarOpen(false);
    } else if (canGoBack) {
      navigate(-1);
    } else {
      void CapacitorApp.exitApp().catch((error) => {
        console.error("Unable to exit the Android app.", error);
      });
    }
  }, [navigate, notificationOpen, productModal, selectedOrder, sidebarOpen]);
  useAndroidBackButton(handleAndroidBackButton);
  const [campaignForm, setCampaignForm] = useState({
    title: "Maison Muse Flash Edit",
    discount_percent: 20,
    stock_allocation: 100,
    duration_minutes: 60,
  });
  const canAccess = (area, right = "read") =>
    Boolean(session?.permissions?.[area]?.[right]);
  const visibleNavItems = NAV_ITEMS.filter((item) => {
    const [area, right] = NAV_ACCESS[item.id];
    return canAccess(area, right);
  });

  const loadData = useCallback(async () => {
    setPageError("");
    try {
      const [
        overviewData,
        productData,
        sellerQcData,
        orderData,
        customerData,
        notificationData,
        campaignData,
        settingsData,
      ] = await Promise.all([
        canAccess("analytics") ? fetchAdminOverview(period) : Promise.resolve(null),
        canAccess("products") ? fetchAdminProducts() : Promise.resolve([]),
        canAccess("products") ? fetchAdminSellerQc() : Promise.resolve([]),
        canAccess("orders") ? fetchAdminOrders() : Promise.resolve([]),
        canAccess("orders") ? fetchAdminCustomers() : Promise.resolve([]),
        canAccess("orders")
          ? fetchAdminNotifications()
          : Promise.resolve({ low_stock: [], new_orders: [] }),
        canAccess("settings") ? fetchAdminCampaigns() : Promise.resolve([]),
        canAccess("settings") ? fetchAdminSettings() : Promise.resolve(null),
      ]);
      setOverview(overviewData);
      setProducts(productData);
      setSellerQc(sellerQcData);
      setOrders(orderData);
      setCustomers(customerData);
      setNotifications(notificationData);
      setCampaigns(campaignData);
      setSettings(settingsData);
    } catch (error) {
      if (error.status === 401) {
        setSession(null);
      } else {
        setPageError(error.message);
      }
    }
  }, [period, session]);

  useEffect(() => {
    let active = true;
    getAdminSession()
      .then((result) => {
        if (active && result.authenticated) setSession(result);
      })
      .catch((error) => {
        if (active) setLoginError(error.message);
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (session) loadData();
  }, [session, loadData]);

  useEffect(() => {
    if (!session) return undefined;
    const timer = window.setInterval(() => {
      if (session.permissions?.orders?.read) {
        fetchAdminNotifications()
          .then(setNotifications)
          .catch((error) => {
            if (error.status === 401) setSession(null);
            else setPageError(error.message);
          });
      }
      if (session.permissions?.settings?.read) {
        fetchAdminCampaigns()
          .then(setCampaigns)
          .catch((error) => {
            if (error.status === 401) setSession(null);
            else setPageError(error.message);
          });
      }
    }, 30000);
    return () => window.clearInterval(timer);
  }, [session]);

  useEffect(() => {
    if (!session || !visibleNavItems.length) return;
    if (!visibleNavItems.some((item) => item.id === page)) {
      setPage(visibleNavItems[0].id);
    }
  }, [page, session, visibleNavItems]);

  useEffect(() => {
    try {
      window.localStorage.setItem("mm-admin-page", page);
      window.localStorage.setItem("mm-admin-period", period);
    } catch {
      setPageError("Dashboard preferences could not be saved in this browser.");
    }
  }, [page, period]);

  const flash = (message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  };

  const withBusy = async (operation, successMessage, rethrow = false) => {
    setBusy(true);
    try {
      await operation();
      await loadData();
      if (successMessage) flash(successMessage);
    } catch (error) {
      setPageError(error.message);
      if (rethrow) throw error;
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleLogin = async (event) => {
    event.preventDefault();
    setBusy(true);
    setLoginError("");
    try {
      const result = await adminLogin(loginForm.username, loginForm.password);
      setSession({ authenticated: true, ...result });
      setLoginForm((current) => ({ ...current, password: "" }));
    } catch (error) {
      setLoginError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = async () => {
    try {
      await adminLogout();
    } catch (error) {
      setPageError(error.message);
    } finally {
      setSession(null);
    }
  };

  const globalResults = useMemo(() => {
    const value = query.trim().toLocaleLowerCase();
    if (!value) return [];
    return [
      ...orders
        .filter((order) =>
          `${order.order_number} ${order.customer.name} ${order.customer.phone}`
            .toLocaleLowerCase()
            .includes(value),
        )
        .slice(0, 4)
        .map((item) => ({ type: "Order", label: item.order_number, id: item.order_number, page: "orders" })),
      ...products
        .filter((product) =>
          `${product.name} ${product.brand} ${product.sku}`
            .toLocaleLowerCase()
            .includes(value),
        )
        .slice(0, 4)
        .map((item) => ({ type: "Product", label: item.name, id: item.id, page: "products" })),
    ];
  }, [orders, products, query]);

  const filteredOrders = useMemo(
    () =>
      orders.filter((order) => {
        const statusMatches = orderFilter === "all" || order.status === orderFilter;
        const searchMatches =
          !query.trim() ||
          `${order.order_number} ${order.customer.name} ${order.customer.phone}`
            .toLocaleLowerCase()
            .includes(query.trim().toLocaleLowerCase());
        return statusMatches && searchMatches;
      }),
    [orders, orderFilter, query],
  );
  const filteredProducts = useMemo(
    () =>
      products.filter((product) =>
        `${product.name} ${product.brand} ${product.sku}`
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase()),
      ),
    [products, query],
  );
  const filteredCustomers = useMemo(
    () =>
      customers.filter((customer) =>
        `${customer.name} ${customer.phone}`
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase()),
      ),
    [customers, query],
  );

  const openOrder = async (orderNumber) => {
    setBusy(true);
    try {
      setSelectedOrder(await fetchAdminOrder(orderNumber));
    } catch (error) {
      setPageError(error.message);
    } finally {
      setBusy(false);
    }
  };

  const changeOrderStatus = async (orderNumber, nextStatus) => {
    await withBusy(async () => {
      const updated = await updateAdminOrderStatus(orderNumber, nextStatus);
      if (selectedOrder?.order_number === orderNumber) {
        setSelectedOrder((current) => ({ ...current, ...updated }));
      }
    }, "Order status updated.");
  };

  const saveProduct = async (payload) => {
    await withBusy(async () => {
      if (productModal?.id) {
        await updateAdminProduct(productModal.id, payload);
      } else {
        await createAdminProduct(payload);
      }
      setProductModal(null);
    }, productModal?.id ? "Product changes saved." : "Product added to the catalog.", true);
  };

  const handleDuplicate = (product) =>
    withBusy(() => duplicateAdminProduct(product.id), "Product duplicated.");
  const handleDelete = (product) => {
    if (window.confirm(`Remove "${product.name}" from the storefront?`)) {
      withBusy(() => deleteAdminProduct(product.id), "Product removed from the storefront.");
    }
  };
  const handleToggleStock = (product) =>
    withBusy(
      () =>
        updateAdminProductStock(
          product.id,
          product.stock > 0 ? 0 : Math.max(10, (product.lowStockThreshold ?? 5) + 1),
        ),
      "Inventory updated.",
    );
  const handleCampaignSubmit = (event) => {
    event.preventDefault();
    withBusy(
      () => createAdminCampaign({
        ...campaignForm,
        discount_percent: Number(campaignForm.discount_percent),
        stock_allocation: Number(campaignForm.stock_allocation),
        duration_minutes: Number(campaignForm.duration_minutes),
      }),
      "Campaign is now live.",
    );
  };
  const toggleStoreStatus = () => {
    const store_status = settings?.store_status === "live" ? "maintenance" : "live";
    withBusy(() => updateAdminSettings({ store_status }), `Store status changed to ${store_status}.`);
  };

  if (checkingSession) {
    return <main className="admin-auth-screen"><div className="admin-auth-card">Preparing secure admin access…</div></main>;
  }
  if (!session) {
    return (
      <main className="admin-auth-screen">
        <form className="admin-auth-card" onSubmit={handleLogin}>
          <Link className="admin-login-brand" to="/">maison <span>muse.</span></Link>
          <span className="admin-overline">PRIVATE STORE ACCESS</span>
          <h1>Welcome back.</h1>
          <p>Sign in to manage your Maison Muse storefront.</p>
          <label>Admin username<input autoComplete="username" required value={loginForm.username} onChange={(e) => setLoginForm((current) => ({ ...current, username: e.target.value }))} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={loginForm.password} onChange={(e) => setLoginForm((current) => ({ ...current, password: e.target.value }))} /></label>
          {loginError && <p className="admin-inline-error" role="alert">{loginError}</p>}
          <button className="admin-button primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in securely"} <ArrowRight size={16} /></button>
          <Link className="admin-back-store" to="/">Return to storefront</Link>
        </form>
      </main>
    );
  }

  const currentTitle =
    visibleNavItems.find((item) => item.id === page)?.label ??
    visibleNavItems[0]?.label ??
    "Admin workspace";
  const totalNotifications =
    notifications.low_stock.length + notifications.new_orders.length;
  const lowStockProducts = products.filter(
    (product) => product.stock <= (product.lowStockThreshold ?? 5),
  );
  const currentDate = new Intl.DateTimeFormat("en-KE", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date()).toUpperCase();
  const currentHour = new Date().getHours();
  const greeting =
    currentHour < 12 ? "Good morning." : currentHour < 18 ? "Good afternoon." : "Good evening.";

  return (
    <div className="admin-shell">
      {sidebarOpen && <button className="admin-mobile-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`admin-sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <Link className="admin-brand" to="/">
          <span className="admin-brand-mark">m.</span>
          <span>maison <strong>muse</strong><small>ADMIN STUDIO</small></span>
        </Link>
        <div className="admin-sidebar-label">WORKSPACE</div>
        <nav className="admin-side-nav" aria-label="Admin sections">
          {visibleNavItems.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={page === id ? "is-active" : ""}
              onClick={() => {
                setPage(id);
                setSidebarOpen(false);
                if (id === "support") navigate("/admin/support");
                else if (window.location.pathname.endsWith("/admin/support")) navigate("/admin");
              }}
            >
              <Icon size={17} />
              <span>{label}</span>
              {id === "orders" && orders.filter((order) => order.status === "pending").length > 0 && (
                <i>{orders.filter((order) => order.status === "pending").length}</i>
              )}
            </button>
          ))}
        </nav>
        <div className="admin-sidebar-bottom">
          <div className="admin-sidebar-help"><CircleHelp size={17} /><span>Need a hand?<small>Admin help center</small></span></div>
          <div className="admin-profile">
            <div className="admin-avatar">{session.username?.slice(0, 1).toUpperCase() ?? "M"}</div>
            <span><strong>{session.username}</strong><small>Administrator</small></span>
            <button type="button" aria-label="Sign out" onClick={handleLogout}><LogOut size={16} /></button>
          </div>
        </div>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <button className="admin-mobile-menu admin-icon-button" aria-label="Open menu" onClick={() => setSidebarOpen(true)}><Menu size={19} /></button>
          <div className="admin-breadcrumb"><span>Maison Muse</span><span>/</span><strong>{currentTitle}</strong></div>
          <div className="admin-top-actions">
            <div className="admin-global-search">
              <Search size={16} />
              <input placeholder="Search products or orders" aria-label="Search products or orders" value={query} onChange={(e) => setQuery(e.target.value)} />
              {query && (
                <div className="admin-search-results">
                  {globalResults.length ? globalResults.map((result) => (
                    <button key={`${result.type}-${result.id}`} onClick={() => { setPage(result.page); setQuery(result.type === "Product" ? result.label : result.id); }}>
                      <span>{result.type}</span><strong>{result.label}</strong><ArrowRight size={14} />
                    </button>
                  )) : <span className="admin-search-empty">No matching records</span>}
                </div>
              )}
            </div>
            <div className="admin-notification-wrap">
              <button className="admin-icon-button admin-bell" aria-label={`${totalNotifications} notifications`} aria-expanded={notificationOpen} onClick={() => setNotificationOpen((open) => !open)}>
                <Bell size={18} />{totalNotifications > 0 && <i>{totalNotifications > 9 ? "9+" : totalNotifications}</i>}
              </button>
              {notificationOpen && (
                <div className="admin-notification-popover">
                  <strong>Store alerts</strong>
                  {notifications.new_orders.map((item) => <button key={item.order_number} onClick={() => { setPage("orders"); setNotificationOpen(false); openOrder(item.order_number); }}><ShoppingBag size={15} /><span>New order {item.order_number}<small>{item.customer_name} · {formatKsh(item.total)}</small></span></button>)}
                  {notifications.low_stock.map((item) => <button key={item.id} onClick={() => { setPage("inventory"); setNotificationOpen(false); }}><Box size={15} /><span>Low stock: {item.name}<small>{item.stock} remaining</small></span></button>)}
                  {!totalNotifications && <p>All caught up. No new store alerts.</p>}
                </div>
              )}
            </div>
            <button className={`admin-live-toggle ${settings?.store_status === "maintenance" ? "is-maintenance" : ""}`} onClick={toggleStoreStatus} disabled={busy || !canAccess("settings", "write")}>
              <span />{settings?.store_status === "maintenance" ? "Maintenance" : "Live"}<ChevronDown size={13} />
            </button>
            <Link className="admin-storefront-link" to="/"><ExternalLink size={15} /><span>View storefront</span></Link>
          </div>
        </header>

        <main className="admin-content">
          <div className="admin-page-heading">
            <div><span className="admin-overline">{currentDate}</span><h1>{page === "overview" ? greeting : currentTitle}</h1><p>{page === "overview" ? "Here’s what’s happening across your beauty store today." : "Manage your Maison Muse store with care and confidence."}</p></div>
            <div className="admin-heading-actions">
              <span className={`admin-status ${settings?.store_status === "maintenance" ? "pending" : "in"}`}><i />Store {settings?.store_status === "maintenance" ? "in maintenance" : "is live"}</span>
              {page === "products" && canAccess("products", "write") && <button className="admin-button primary" onClick={() => setProductModal("new")}><Plus size={16} /> Add product</button>}
              {page === "overview" && <button className="admin-button secondary" onClick={loadData}><Activity size={15} /> Refresh data</button>}
            </div>
          </div>
          {pageError && <div className="admin-alert" role="alert"><ShieldCheck size={17} />{pageError}<button onClick={() => setPageError("")} aria-label="Dismiss"><X size={15} /></button></div>}

          {page === "overview" && (
            <>
              <section className="admin-kpi-grid">
                {[
                  { label: "Total revenue", value: formatKsh(overview?.kpis.revenue ?? 0), trend: overview?.trends.revenue_percent ?? 0, icon: Activity },
                  { label: "Total orders", value: overview?.kpis.orders ?? 0, trend: overview?.trends.orders_percent ?? 0, icon: ShoppingBag },
                  { label: "Average order value", value: formatKsh(overview?.kpis.average_order_value ?? 0), trend: overview?.trends.aov_percent ?? 0, icon: CreditCard },
                  { label: "Active customers", value: overview?.kpis.active_customers ?? 0, trend: overview?.trends.customers_percent ?? 0, icon: Users },
                ].map(({ label, value, trend, icon: Icon }) => (
                  <article className="admin-kpi-card" key={label}>
                    <span className="admin-kpi-icon"><Icon size={17} /></span>
                    <span className="admin-kpi-label">{label}</span>
                    <strong>{value}</strong>
                    <small className={trend >= 0 ? "trend-up" : "trend-down"}>
                      {trend >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {Math.abs(trend).toFixed(1)}% <i>vs previous period</i>
                    </small>
                  </article>
                ))}
                <article className="admin-kpi-card stock-kpi">
                  <span className="admin-kpi-icon"><Box size={17} /></span>
                  <span className="admin-kpi-label">Low stock alerts</span>
                  <strong>{overview?.kpis.low_stock ?? 0}</strong>
                  <button onClick={() => setPage("inventory")}>Review inventory <ArrowRight size={13} /></button>
                </article>
              </section>
              <section className="admin-overview-grid">
                <article className="admin-panel admin-revenue-panel">
                  <header className="admin-panel-heading">
                    <div><span className="admin-overline">STORE PERFORMANCE</span><h2>Revenue & sales trend</h2></div>
                    <div className="admin-period-tabs">{["daily", "weekly", "monthly"].map((item) => <button className={period === item ? "is-active" : ""} key={item} onClick={() => setPeriod(item)}>{item}</button>)}</div>
                  </header>
                  <div className="admin-chart-legend"><span><i /> Revenue (KSh)</span><span><i /> Orders</span><strong>{formatKsh(overview?.kpis.revenue ?? 0)}<small>all-time revenue</small></strong></div>
                  <RevenueChart points={overview?.chart ?? []} period={period} />
                </article>
                {canAccess("orders") && <article className="admin-panel admin-recent-panel">
                  <header className="admin-panel-heading"><div><span className="admin-overline">THE LATEST</span><h2>Recent orders</h2></div><button className="admin-text-link" onClick={() => setPage("orders")}>View all <ArrowRight size={13} /></button></header>
                  <div className="admin-recent-list">{(overview?.recent_orders ?? []).slice(0, 5).map((order) => <button className="admin-recent-order" key={order.order_number} onClick={() => openOrder(order.order_number)}><span className="admin-order-avatar">{order.customer.name.slice(0, 1)}</span><span><strong>{order.customer.name}</strong><small>{order.order_number} · {formatDate(order.created_at)}</small></span><b>{formatKsh(order.total)}</b><i className={`admin-status-dot ${order.status}`} /></button>)}
                    {!overview?.recent_orders?.length && <p className="admin-empty-copy">Orders will appear here when customers check out.</p>}
                  </div>
                </article>}
              </section>
              <section className="admin-panel admin-top-products">
                <header className="admin-panel-heading"><div><span className="admin-overline">CUSTOMER FAVORITES</span><h2>Top-selling beauty products</h2></div><button className="admin-text-link" onClick={() => setPage("products")}>Manage catalog <ArrowRight size={13} /></button></header>
                <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Product</th><th>Units sold</th><th>Revenue</th><th>Performance</th></tr></thead><tbody>{(overview?.top_products ?? []).map((product, index) => <tr key={product.id}><td><span className="admin-rank">{String(index + 1).padStart(2, "0")}</span><strong>{product.name}</strong></td><td>{product.units_sold}</td><td>{formatKsh(product.revenue)}</td><td><span className="admin-performance-bar"><i style={{ width: `${Math.max(12, 100 - index * 12)}%` }} /></span></td></tr>)}
                  {!overview?.top_products?.length && <tr><td colSpan="4" className="admin-empty-copy">Sales rankings will appear after the first order.</td></tr>}
                </tbody></table></div>
              </section>
            </>
          )}

          {(page === "products" || page === "inventory") && (
            <section className="admin-panel admin-data-panel">
              <header className="admin-panel-heading">
                <div><span className="admin-overline">{page === "inventory" ? "STOCK HEALTH" : "YOUR BEAUTY EDIT"}</span><h2>{page === "inventory" ? "Inventory overview" : "Product catalog"} <small>{page === "inventory" ? lowStockProducts.length : filteredProducts.length} {page === "inventory" ? "alerts" : "products"}</small></h2></div>
                <div className="admin-table-tools"><label className="admin-table-search"><Search size={15} /><input placeholder="Find product or SKU" value={query} onChange={(e) => setQuery(e.target.value)} /></label>{page === "inventory" && <button className="admin-button secondary" onClick={() => setProducts([...products].sort((a, b) => a.stock - b.stock))}>Sort by stock</button>}</div>
              </header>
              <div className="admin-table-scroll"><table className="admin-table product-admin-table"><thead><tr><th>Product</th><th>Category</th><th>SKU</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th></tr></thead><tbody>
                {(page === "inventory" ? filteredProducts.filter((product) => product.stock <= (product.lowStockThreshold ?? 5)) : filteredProducts).map((product) => { const stock = stockState(product); return <tr key={product.id}><td><span className="admin-product-cell"><img src={product.image} alt="" /><span><strong>{product.name}</strong><small>{product.brand}</small></span></span></td><td>{product.category}</td><td><code>{product.sku}</code></td><td>{formatKsh(product.price)}</td><td><strong>{product.stock}</strong><small className="admin-stock-threshold">Alert at {product.lowStockThreshold ?? 5}</small></td><td><span className={`admin-status ${stock.className}`}><i />{stock.label}</span></td><td><span className="admin-row-actions"><button title="Edit product" aria-label={`Edit ${product.name}`} disabled={!canAccess("products", "write")} onClick={() => setProductModal(product)}><Pencil size={15} /></button><button title="Duplicate product" aria-label={`Duplicate ${product.name}`} disabled={!canAccess("products", "write")} onClick={() => handleDuplicate(product)}><Copy size={15} /></button><button title={product.stock ? "Mark out of stock" : "Restock"} aria-label={product.stock ? `Mark ${product.name} out of stock` : `Restock ${product.name}`} disabled={!canAccess("products", "write")} onClick={() => handleToggleStock(product)}><Box size={15} /></button><button className="danger" title="Delete product" aria-label={`Delete ${product.name}`} disabled={!canAccess("products", "delete")} onClick={() => handleDelete(product)}><Trash2 size={15} /></button></span></td></tr>; })}
                {!filteredProducts.length && <tr><td colSpan="7" className="admin-empty-copy">No products match this search.</td></tr>}
                {page === "inventory" && !lowStockProducts.length && <tr><td colSpan="7" className="admin-empty-copy">Lovely! Every active item is above its low-stock threshold.</td></tr>}
              </tbody></table></div>
            </section>
          )}

          {page === "sellerQc" && (
            <section className="admin-panel admin-data-panel">
              <header className="admin-panel-heading">
                <div><span className="admin-overline">SELLER CATALOG REVIEW</span><h2>Quality control queue <small>{sellerQc.length} pending</small></h2></div>
                <button className="admin-button secondary" type="button" onClick={loadData}><Activity size={15} /> Refresh queue</button>
              </header>
              <div className="admin-seller-qc-list">
                {sellerQc.map((product) => (
                  <article key={product.id}>
                    <img src={product.image} alt="" />
                    <div><strong>{product.name}</strong><small>{product.brand} · {product.sku} · {product.category}</small><small>{product.store_name} · {product.qc_status.replaceAll("_", " ")}</small>{product.notes && <p>{product.notes}</p>}</div>
                    <div className="admin-row-actions">
                      <button className="admin-button primary" type="button" disabled={!canAccess("products", "write") || busy} onClick={() => withBusy(() => decideAdminSellerQc(product.id, { action: "APPROVE", notes: "Quality review passed." }), "Seller listing approved and published.")}><Check size={14} /> Approve</button>
                      <button className="admin-button secondary" type="button" disabled={!canAccess("products", "write") || busy} onClick={() => withBusy(() => decideAdminSellerQc(product.id, { action: "REJECT", notes: "Please improve image quality before resubmission." }), "Listing rejected; seller can resubmit after updating it.")}>Reject image</button>
                    </div>
                  </article>
                ))}
                {!sellerQc.length && <p className="admin-empty-copy">No seller listings are waiting for review.</p>}
              </div>
            </section>
          )}

          {page === "orders" && (
            <section className="admin-panel admin-data-panel">
              <header className="admin-panel-heading"><div><span className="admin-overline">PACKING & DELIVERY</span><h2>Orders <small>{filteredOrders.length} results</small></h2></div><label className="admin-table-search"><Search size={15} /><input placeholder="Search order or customer" value={query} onChange={(e) => setQuery(e.target.value)} /></label></header>
              <div className="admin-order-filters">{ORDER_FILTERS.map((filter) => <button className={orderFilter === filter ? "is-active" : ""} onClick={() => setOrderFilter(filter)} key={filter}>{filter === "all" ? "All orders" : statusLabel(filter)}</button>)}</div>
              <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Order</th><th>Customer</th><th>Date</th><th>Payment</th><th>Total</th><th>Status</th><th>View</th></tr></thead><tbody>{filteredOrders.map((order) => <tr key={order.order_number}><td><strong>{order.order_number}</strong></td><td><strong>{order.customer.name}</strong><small className="admin-stock-threshold">{order.customer.phone}</small></td><td>{formatDate(order.created_at)}</td><td>{order.payment_method === "pesapal" ? "Pesapal" : order.payment_method === "mobile-money" ? "M-Pesa" : order.payment_method === "card" ? "Card" : "Cash on delivery"}</td><td><strong>{formatKsh(order.total)}</strong></td><td><span className={`admin-status ${order.status}`}><i />{statusLabel(order.status)}</span></td><td><button className="admin-row-action" aria-label={`View ${order.order_number}`} onClick={() => openOrder(order.order_number)}><Eye size={16} /></button></td></tr>)}
                {!filteredOrders.length && <tr><td colSpan="7" className="admin-empty-copy">No orders match the selected filters.</td></tr>}
              </tbody></table></div>
            </section>
          )}

          {page === "customers" && (
            <section className="admin-panel admin-data-panel"><header className="admin-panel-heading"><div><span className="admin-overline">YOUR COMMUNITY</span><h2>Customer directory <small>{filteredCustomers.length} customers</small></h2></div><label className="admin-table-search"><Search size={15} /><input placeholder="Search name or phone" value={query} onChange={(e) => setQuery(e.target.value)} /></label></header>
              <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Customer</th><th>Phone</th><th>Delivery address</th><th>Orders</th><th>Lifetime spend</th><th>Last order</th></tr></thead><tbody>{filteredCustomers.map((customer) => <tr key={`${customer.phone}-${customer.name}`}><td><span className="admin-customer-cell"><span className="admin-order-avatar">{customer.name.slice(0, 1)}</span><strong>{customer.name}</strong></span></td><td><a href={`tel:${customer.phone}`}>{customer.phone}</a></td><td className="admin-address-cell">{customer.address}</td><td>{customer.order_count}</td><td><strong>{formatKsh(customer.total_spend)}</strong></td><td>{formatDate(customer.last_order)}</td></tr>)}
                {!filteredCustomers.length && <tr><td colSpan="6" className="admin-empty-copy">Customer profiles are created when an order is placed. No email is collected at checkout.</td></tr>}
              </tbody></table></div>
            </section>
          )}

          {page === "security" && <SecurityManager adminRole={session.role} canManageSessions={canAccess("settings", "write")} />}
          {page === "audit" && <AuditLogs />}
          {page === "payments" && <PaymentLogs canReconcile={canAccess("orders", "write")} />}
          {page === "insights" && <CustomerInsights />}
          {page === "suppliers" && <SupplierManager canWrite={canAccess("products", "write")} />}
          {page === "vendors" && <VendorManager />}
          {page === "commissions" && <CommissionManager />}
          {page === "marketplaceOrders" && <AdminOrders canManage={canAccess("orders", "write")} />}
          {page === "marketplaceAnalytics" && <AnalyticsOverview />}
          {page === "support" && (
            <AdminSupport canWrite={canAccess("support", "write")} />
          )}

          {page === "campaigns" && (
            <div className="admin-campaign-layout">
              <section className="admin-panel admin-campaign-form-panel"><header className="admin-panel-heading"><div><span className="admin-overline">PROMOTION STUDIO</span><h2>Launch a campaign</h2></div><Sparkles size={20} /></header>
                <form className="admin-campaign-form" onSubmit={handleCampaignSubmit}>
                  <label>Campaign title<input required minLength="3" maxLength="120" value={campaignForm.title} onChange={(e) => setCampaignForm({ ...campaignForm, title: e.target.value })} /></label>
                  <label>Discount percentage <span className="admin-input-suffix"><input type="number" min="1" max="90" value={campaignForm.discount_percent} onChange={(e) => setCampaignForm({ ...campaignForm, discount_percent: e.target.value })} /><b>%</b></span></label>
                  <label>Allocated campaign stock<input type="number" min="0" value={campaignForm.stock_allocation} onChange={(e) => setCampaignForm({ ...campaignForm, stock_allocation: e.target.value })} /></label>
                  <label>Countdown duration<select value={campaignForm.duration_minutes} onChange={(e) => setCampaignForm({ ...campaignForm, duration_minutes: e.target.value })}><option value="30">30 minutes</option><option value="60">1 hour</option><option value="180">3 hours</option><option value="360">6 hours</option><option value="1440">24 hours</option><option value="10080">7 days</option></select></label>
                  <button className="admin-button primary" type="submit" disabled={busy || !canAccess("settings", "write")}><Sparkles size={15} /> Launch flash campaign</button>
                  <p className="admin-form-note"><ShieldCheck size={14} /> Campaigns are saved to the store database. Discounts are campaign metadata and are not yet applied to checkout prices.</p>
                </form>
              </section>
              <section className="admin-panel admin-campaign-list"><header className="admin-panel-heading"><div><span className="admin-overline">CAMPAIGN HISTORY</span><h2>Your campaigns</h2></div></header>
                {!campaigns.length && <p className="admin-empty-copy">Your live and past campaigns will appear here.</p>}
                {campaigns.map((campaign) => <article className={`admin-campaign-card ${campaign.active ? "is-live" : ""}`} key={campaign.id}><div className="admin-campaign-card-top"><span className={`admin-status ${campaign.active ? "in" : "pending"}`}><i />{campaign.active ? "Live now" : "Ended"}</span><span>{campaign.discount_percent}% OFF</span></div><h3>{campaign.title}</h3><div className="admin-campaign-meta"><span><Box size={14} />{campaign.stock_allocation} units</span>{campaign.active ? <CampaignCountdown endsAt={campaign.ends_at} /> : <span><Clock3 size={14} />{campaign.duration_minutes} min</span>}</div><p>{formatDate(campaign.starts_at)} — {formatDate(campaign.ends_at)}</p>{campaign.active && <button className="admin-button secondary" disabled={!canAccess("settings", "write")} onClick={() => withBusy(() => deactivateAdminCampaign(campaign.id), "Campaign ended.")}><Pause size={14} /> End campaign</button>}</article>)}
              </section>
            </div>
          )}

          {page === "settings" && (
            <section className="admin-panel admin-settings-panel"><header className="admin-panel-heading"><div><span className="admin-overline">STORE CONTROL</span><h2>System settings</h2></div><Settings size={19} /></header>
              <article className="admin-setting-row"><span className="admin-setting-icon"><Store size={18} /></span><span><strong>Storefront availability</strong><small>Maintenance mode pauses the public storefront while you work on the catalog.</small></span><button className={`admin-live-toggle ${settings?.store_status === "maintenance" ? "is-maintenance" : ""}`} onClick={toggleStoreStatus} disabled={busy || !canAccess("settings", "write")}><span />{settings?.store_status === "maintenance" ? "Maintenance" : "Live"}<ChevronDown size={13} /></button></article>
              <article className="admin-setting-row"><span className="admin-setting-icon"><CreditCard size={18} /></span><span><strong>Store currency</strong><small>Catalog and checkout prices are displayed in Kenyan shillings.</small></span><b>KES · KSh</b></article>
              <article className="admin-setting-row"><span className="admin-setting-icon"><Clock3 size={18} /></span><span><strong>Store time zone</strong><small>Campaign timers and order records use the Nairobi time zone.</small></span><b>Africa/Nairobi</b></article>
              <article className="admin-setting-row"><span className="admin-setting-icon"><ShieldCheck size={18} /></span><span><strong>Admin security</strong><small>Session uses a signed, HTTP-only cookie and same-site request protections.</small></span><b>{session.username}</b></article>
            </section>
          )}
        </main>
      </div>
      {toast && <div className="admin-toast" role="status"><Check size={16} />{toast}</div>}
      {productModal !== null && page === "products" && productModal !== "closed" && (
        <ProductModal
          key={productModal?.id ?? "new-product"}
          product={productModal === "new" ? null : productModal}
          saving={busy}
          onClose={() => setProductModal(null)}
          onSave={saveProduct}
        />
      )}
      {selectedOrder && <OrderModal order={selectedOrder} saving={busy} canUpdate={canAccess("orders", "write")} onClose={() => setSelectedOrder(null)} onStatusChange={changeOrderStatus} />}
    </div>
  );
}

export default AdminDashboard;
