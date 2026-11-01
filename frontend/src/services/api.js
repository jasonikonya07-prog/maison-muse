const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ?? "";

async function publicApiRequest(path, fallback) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(fallback);
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The API returned invalid JSON.");
  }
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, `The request failed (${response.status}).`),
    );
  }
  return payload;
}

function getApiErrorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    const messages = payload.detail
      .map((issue) => issue?.msg)
      .filter((message) => typeof message === "string");
    if (messages.length > 0) return messages.join(" ");
  }
  if (typeof payload?.message === "string") return payload.message;
  return fallback;
}

async function adminRequest(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/admin${path}`, {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-Admin-Request": "1" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the admin API. Check that the backend is running.");
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The admin API returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The admin request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function sellerRequest(path, { method = "GET", body, signal } = {}) {
  let token = "";
  try {
    token =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/seller${path}`, {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-Seller-Request": "1" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the seller API. Check that the backend is running.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The seller API returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The seller request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function sellerApiRequest(path, { method = "GET", body, signal } = {}) {
  let token = "";
  try {
    token =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api${path}`, {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-Seller-Request": "1" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the seller API. Check that the backend is running.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The seller API returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The seller request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function authRequest(path, body) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/auth${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the authentication service. Check that the backend is running.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The authentication service returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The sign-in request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const registerAccount = (details) => authRequest("/register", details);
export const loginAccount = (email, password) =>
  authRequest("/login", { email, password });
export const loginWithGoogle = (credential) =>
  authRequest("/google", { credential });
export const loginWithGoogleDemo = () =>
  authRequest("/google", { simulation: true });

export const registerSeller = (details) =>
  sellerRequest("/register", { method: "POST", body: details });
export const sellerLogin = (email, password) =>
  sellerRequest("/login", { method: "POST", body: { email, password } });
export const sellerLogout = () => sellerRequest("/logout", { method: "POST" });
export const fetchSellerMe = () => sellerRequest("/me");
export const fetchSellerDashboard = (period = "30d") =>
  sellerRequest(`/dashboard?period=${encodeURIComponent(period)}`);
export const updateSellerProfile = (profile) =>
  sellerRequest("/profile", { method: "PUT", body: profile });
export const uploadSellerImage = async (file) => {
  let token = "";
  try {
    token =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  const body = new FormData();
  body.append("image", file);
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/seller/uploads`, {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "X-Seller-Request": "1",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
    });
  } catch {
    throw new Error("Could not reach the seller API. Check that the backend is running.");
  }
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    if (response.ok) throw new Error("The seller API returned invalid JSON.");
  }
  if (!response.ok) {
    throw new Error(getApiErrorMessage(payload, `The seller request failed (${response.status}).`));
  }
  return payload;
};
export const fetchSellerPayouts = () => sellerRequest("/payouts");
export const simulateSellerPayout = (details) =>
  sellerRequest("/withdraw", { method: "POST", ...(details ? { body: details } : {}) });
export const requestSellerProfileUpdate = (details) =>
  sellerRequest("/request-profile-update", { method: "POST", body: details });
export const verifySellerProfileUpdate = (code) =>
  sellerRequest("/verify-profile-update", { method: "POST", body: { code } });
export const fetchSellerProducts = () => sellerRequest("/products");
export const updateSellerPlan = (selected_plan) =>
  sellerRequest("/plan", { method: "PUT", body: { selected_plan } });
export const upgradeSellerPlan = (details) =>
  sellerRequest("/upgrade-plan", { method: "POST", body: details });
export const createSellerProduct = (product) =>
  sellerRequest("/products", { method: "POST", body: product });
export const updateSellerProduct = (id, product) =>
  sellerRequest(`/products/${encodeURIComponent(id)}`, { method: "PUT", body: product });
export const deleteSellerProduct = (id) =>
  sellerRequest(`/products/${encodeURIComponent(id)}`, { method: "DELETE" });
export const fetchSellerOrders = () => sellerRequest("/orders");
export const updateSellerFulfillment = (id, fulfillmentStatus, dispatch = {}) =>
  sellerRequest(`/orders/${id}/status`, {
    method: "PUT",
    body: { status: fulfillmentStatus, ...dispatch },
  });
export const updateSellerOrder = (id, fulfillmentStatus, dispatch = {}) =>
  sellerApiRequest(`/orders/${id}/status`, {
    method: "PUT",
    body: { status: fulfillmentStatus, ...dispatch },
  });
export const bulkUpdateSellerProducts = (details) =>
  sellerRequest("/products/bulk", { method: "POST", body: details });
export const fetchSellerHealth = () => sellerRequest("/health");
export const fetchSellerPromotions = () => sellerApiRequest("/seller/promotions");
export const fetchSellerCampaigns = () => sellerApiRequest("/seller/campaigns");
export const enrollSellerCampaign = (campaignId, product_ids) =>
  sellerApiRequest(`/seller/campaigns/${encodeURIComponent(campaignId)}/enroll`, {
    method: "POST",
    body: { product_ids },
  });
export const createSellerPromotion = (promotion) =>
  sellerApiRequest("/promotions", { method: "POST", body: promotion });
export const fetchSellerReturns = () => sellerRequest("/returns");
export const updateSellerReturn = (id, update) =>
  sellerApiRequest(`/returns/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: update,
  });
export const fetchSellerAds = () => sellerRequest("/ads");
export const boostSellerProduct = (details) =>
  sellerApiRequest("/products/boost", { method: "POST", body: details });
export const fetchSellerProductCsvTemplate = () =>
  sellerApiRequest("/seller/products/csv-template");
export const fetchSellerTeam = () => sellerApiRequest("/seller/team");
export const inviteSellerTeamMember = (details) =>
  sellerApiRequest("/seller/team", { method: "POST", body: details });
export const revokeSellerTeamMember = (id) =>
  sellerApiRequest(`/seller/team/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: { status: "REVOKED" },
  });
export const fetchSellerMessages = () => sellerApiRequest("/seller/messages");
export const replyToSellerMessage = (details) =>
  sellerApiRequest("/seller/messages/reply", { method: "POST", body: details });
export const startBuyerSellerConversation = (details) =>
  sellerApiRequest("/messages", { method: "POST", body: details });
export const fetchBuyerSellerConversation = (conversationId) =>
  sellerApiRequest(`/messages/${encodeURIComponent(conversationId)}`);
export const replyToBuyerSellerConversation = (conversationId, body) =>
  sellerApiRequest(`/messages/${encodeURIComponent(conversationId)}`, {
    method: "POST",
    body: { body },
  });
export const fetchSellerNotificationPreferences = () =>
  sellerApiRequest("/seller/notifications");
export const updateSellerNotificationPreferences = (details) =>
  sellerApiRequest("/seller/notifications", { method: "PUT", body: details });
export const fetchSellerFulfillment = () => sellerApiRequest("/seller/fulfillment");
export const updateSellerFulfillmentMode = (productId, fulfillment_mode) =>
  sellerApiRequest(`/seller/products/${encodeURIComponent(productId)}/fulfillment`, {
    method: "PUT",
    body: { fulfillment_mode },
  });
export const fetchSellerManifests = () =>
  sellerApiRequest("/seller/logistics/manifests");
export const createSellerManifest = (details) =>
  sellerApiRequest("/seller/logistics/manifests", { method: "POST", body: details });
export const confirmSellerManifestDropoff = (id) =>
  sellerApiRequest(`/seller/logistics/manifests/${encodeURIComponent(id)}/dropoff`, {
    method: "POST",
    body: {},
  });
export const fetchSellerQcQueue = () => sellerApiRequest("/seller/qc");
export const submitSellerProductQc = (productId) =>
  sellerApiRequest(`/seller/products/${encodeURIComponent(productId)}/qc`, {
    method: "POST",
    body: {},
  });
export const createSellerVasRequest = (details) =>
  sellerApiRequest("/seller/vas-requests", { method: "POST", body: details });
export const fetchSellerWeeklyStatement = () =>
  sellerApiRequest("/seller/statements/weekly");
export const fetchSellerRepricingRules = () =>
  sellerApiRequest("/seller/repricing");
export const updateSellerRepricingRule = (productId, details) =>
  sellerApiRequest(`/seller/products/${encodeURIComponent(productId)}/repricing`, {
    method: "PUT",
    body: details,
  });
export const fetchSellerBranches = () => sellerApiRequest("/seller/branches");
export const createSellerBranch = (details) =>
  sellerApiRequest("/seller/branches", { method: "POST", body: details });
export const updateSellerBranchInventory = (branchId, items) =>
  sellerApiRequest(`/seller/branches/${encodeURIComponent(branchId)}/inventory`, {
    method: "PUT",
    body: { items },
  });
export const fetchSellerRestockPlan = () => sellerApiRequest("/seller/restock");
export const requestSellerRestock = (productId, recommended_quantity) =>
  sellerApiRequest(`/seller/products/${encodeURIComponent(productId)}/restock`, {
    method: "POST",
    body: { recommended_quantity },
  });
export const requestSellerOrderReview = (orderId, channel) =>
  sellerApiRequest(`/seller/orders/${encodeURIComponent(orderId)}/review-request`, {
    method: "POST",
    body: { channel },
  });
export const fetchSellerInsights = () => sellerApiRequest("/seller/insights");
export const uploadSellerProductsCsv = async (file) => {
  let token = "";
  try {
    token =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  const body = new FormData();
  body.append("file", file);
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/products/bulk-upload`, {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "X-Seller-Request": "1",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the seller API. Check that the backend is running.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The seller API returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The seller request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
};
export const approveSellerSelf = () =>
  sellerRequest("/approve-self", { method: "PUT" });
export const approveAllSellersForDevelopment = () =>
  sellerRequest("/approve-all", { method: "POST" });
export const fetchPublicStore = (slug) =>
  sellerRequest(`/stores/${encodeURIComponent(slug)}`);
export const fetchPublicSellerBySlug = (slug) =>
  sellerApiRequest(`/sellers/${encodeURIComponent(slug)}`);

export const getAdminSession = () => adminRequest("/session");
export const adminLogin = (username, password) =>
  adminRequest("/login", { method: "POST", body: { username, password } });
export const adminLogout = () => adminRequest("/logout", { method: "POST" });
export const fetchAdminOverview = (period = "weekly") =>
  adminRequest(`/overview?period=${encodeURIComponent(period)}`);
export const fetchAdminProducts = (search = "") =>
  adminRequest(`/products${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const fetchAdminSellerQc = () => adminRequest("/seller-qc");
export const decideAdminSellerQc = (productId, review) =>
  adminRequest(`/seller-qc/${encodeURIComponent(productId)}`, {
    method: "POST",
    body: review,
  });
export const createAdminProduct = (product) =>
  adminRequest("/products", { method: "POST", body: product });
export const updateAdminProduct = (id, product) =>
  adminRequest(`/products/${encodeURIComponent(id)}`, { method: "PUT", body: product });
export const duplicateAdminProduct = (id) =>
  adminRequest(`/products/${encodeURIComponent(id)}/duplicate`, { method: "POST" });
export const deleteAdminProduct = (id) =>
  adminRequest(`/products/${encodeURIComponent(id)}`, { method: "DELETE" });
export const updateAdminProductStock = (id, stock) =>
  adminRequest(`/products/${encodeURIComponent(id)}/stock?stock=${stock}`, { method: "PATCH" });
export const fetchAdminOrders = (status = "all", search = "") => {
  const params = new URLSearchParams();
  if (status !== "all") params.set("status", status);
  if (search) params.set("search", search);
  return adminRequest(`/orders${params.size ? `?${params}` : ""}`);
};
export const fetchAdminFulfillmentOrders = ({
  vendorId = "",
  status = "",
  search = "",
} = {}) => {
  const params = new URLSearchParams({ scope: "fulfillment" });
  if (vendorId) params.set("vendor_id", vendorId);
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  return adminRequest(`/orders?${params}`);
};
export const fetchAdminOrder = (orderNumber) =>
  adminRequest(`/orders/${encodeURIComponent(orderNumber)}`);
export const updateAdminFulfillmentStatus = (id, update) =>
  adminRequest(`/orders/${encodeURIComponent(id)}/override-status`, {
    method: "PUT",
    body: update,
  });
export const updateAdminOrderStatus = (orderNumber, status) =>
  adminRequest(`/orders/${encodeURIComponent(orderNumber)}/status`, {
    method: "PATCH",
    body: { status },
  });
export const fetchAdminCustomers = (search = "") =>
  adminRequest(`/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const fetchAdminUserActivity = (search = "") =>
  adminRequest(`/users${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const fetchMarketplaceVendorWarnings = (sellerId) =>
  adminRequest(`/marketplace/vendors/${encodeURIComponent(sellerId)}/warnings`);
export const createMarketplaceVendorWarning = (sellerId, warning) =>
  adminRequest(`/marketplace/vendors/${encodeURIComponent(sellerId)}/warnings`, {
    method: "POST",
    body: warning,
  });
export const fetchAdminNotifications = () => adminRequest("/notifications");
export const fetchAdminCampaigns = () => adminRequest("/campaigns");
export const createAdminCampaign = (campaign) =>
  adminRequest("/campaigns", { method: "POST", body: campaign });
export const deactivateAdminCampaign = (id) =>
  adminRequest(`/campaigns/${id}`, { method: "DELETE" });
export const fetchAdminSettings = () => adminRequest("/settings");
export const updateAdminSettings = (settings) =>
  adminRequest("/settings", { method: "PUT", body: settings });
export const fetchAdminSessions = () => adminRequest("/security/sessions");
export const revokeAdminSession = (sessionId) =>
  adminRequest(`/security/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
export const fetchAdminRoles = () => adminRequest("/security/roles");
export const updateAdminRole = (role, permissions) =>
  adminRequest(`/security/roles/${encodeURIComponent(role)}`, {
    method: "PUT",
    body: { permissions },
  });
export const fetchAdminSecurityAlerts = () => adminRequest("/security/alerts");
export const fetchAdminAuditLogs = (filters = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  return adminRequest(`/audit-logs${params.size ? `?${params}` : ""}`);
};
export const downloadAdminAuditLogs = async (filters, format) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  params.set("export", format);
  const response = await fetch(
    `${API_BASE_URL}/api/admin/audit-logs?${params}`,
    {
      credentials: "include",
      headers: { Accept: format === "csv" ? "text/csv" : "application/json" },
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = new Error(
      getApiErrorMessage(payload, `The audit export failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return response.blob();
};

async function supportRequest(path, { method = "GET", body, token, signal } = {}) {
  let authToken = "";
  try {
    authToken =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token") ??
      "";
  } catch (error) {
    console.error("Unable to read the saved account session for support.", error);
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/support${path}`, {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { "X-Support-Token": token } : {}),
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach Maison Muse support. Please try again.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The support API returned invalid JSON.");
  }
  if (!response.ok) {
    const error = new Error(
      getApiErrorMessage(payload, `The support request failed (${response.status}).`),
    );
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const sendSupportMessage = (message, token = "") =>
  supportRequest("/message", {
    method: "POST",
    body: message,
    token,
  });
export const fetchSupportTicket = (ticketId, token) =>
  supportRequest(`/tickets/${encodeURIComponent(ticketId)}`, { token });

export function createSupportWebSocket(ticketId, { onMessage, onOpen, onClose } = {}) {
  const socketUrl = new URL(
    `/ws/support/${encodeURIComponent(ticketId)}`,
    API_BASE_URL || window.location.origin,
  );
  socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(socketUrl);
  socket.addEventListener("message", (event) => {
    try {
      onMessage?.(JSON.parse(event.data));
    } catch (error) {
      console.error("The support socket sent an invalid event.", error);
    }
  });
  socket.addEventListener("open", () => onOpen?.());
  socket.addEventListener("close", (event) => onClose?.(event));
  return socket;
}

export function createOrderWebSocket(trackingId, { onMessage, onOpen, onClose } = {}) {
  const socketUrl = new URL(
    `/ws/orders/${encodeURIComponent(trackingId)}`,
    API_BASE_URL || window.location.origin,
  );
  socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(socketUrl);
  socket.addEventListener("message", (event) => {
    try {
      onMessage?.(JSON.parse(event.data));
    } catch (error) {
      console.error("The order tracking socket sent an invalid event.", error);
    }
  });
  socket.addEventListener("open", () => onOpen?.());
  socket.addEventListener("close", (event) => onClose?.(event));
  return socket;
}

export const fetchAdminSupportTickets = (status = "all") =>
  adminRequest(`/support/tickets?status=${encodeURIComponent(status)}`);
export const fetchAdminSupportTicket = (ticketId) =>
  adminRequest(`/support/tickets/${encodeURIComponent(ticketId)}`);
export const replyAdminSupportTicket = (ticket_id, message) =>
  adminRequest("/support/reply", {
    method: "POST",
    body: { ticket_id, message },
  });
export const updateAdminSupportTicketStatus = (ticketId, status) =>
  adminRequest(`/support/tickets/${encodeURIComponent(ticketId)}/status`, {
    method: "PATCH",
    body: { status },
  });
export const fetchAdminPayments = (search = "") =>
  adminRequest(`/payments${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const reconcileAdminPayment = (orderNumber) =>
  adminRequest(`/payments/${encodeURIComponent(orderNumber)}/reconcile`, {
    method: "POST",
  });
export const fetchAdminCustomerInsights = () =>
  adminRequest("/customer-insights");
export const fetchSupplierOverview = () =>
  adminRequest("/suppliers/overview");
export const updateAdminProductCost = (productId, unitCost) =>
  adminRequest(`/products/${encodeURIComponent(productId)}/cost`, {
    method: "PATCH",
    body: { unit_cost: unitCost },
  });
export const draftLowStockPurchaseOrders = () =>
  adminRequest("/suppliers/purchase-orders/draft-low-stock", { method: "POST" });
export const fetchMarketplaceManagement = () => adminRequest("/marketplace");
export const updateMarketplaceVendor = (id, status) =>
  adminRequest(`/marketplace/vendors/${id}`, { method: "PATCH", body: { status } });
export const reviewMarketplaceVendor = (id, action, reason = "") =>
  adminRequest(`/marketplace/vendors/${id}/review`, {
    method: "POST",
    body: { action, reason },
  });
export const fetchMarketplaceCommissions = () =>
  adminRequest("/marketplace/commissions");
export const updateMarketplaceCommissions = (settings) =>
  adminRequest("/marketplace/commissions", { method: "PUT", body: settings });
export const createMarketplacePayout = (payout) =>
  adminRequest("/marketplace/payouts", { method: "POST", body: payout });
export const updateMarketplacePayout = (id, update) =>
  adminRequest(`/marketplace/payouts/${id}`, { method: "PATCH", body: update });
export const fetchMarketplaceOrders = ({ sellerId = "", status = "" } = {}) => {
  const params = new URLSearchParams();
  if (sellerId) params.set("seller_id", sellerId);
  if (status) params.set("status", status);
  return adminRequest(`/marketplace/orders${params.size ? `?${params}` : ""}`);
};
export const fetchMarketplaceOrderSellers = () =>
  adminRequest("/marketplace/orders/sellers");
export const createMarketplaceDispute = (subOrderId, dispute) =>
  adminRequest(`/marketplace/orders/${subOrderId}/disputes`, {
    method: "POST",
    body: dispute,
  });
export const fetchMarketplaceAnalytics = () =>
  adminRequest("/marketplace/analytics");
export async function fetchStorefrontStatus() {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/admin/storefront/status`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new Error("Could not reach the storefront status service.");
  }
  if (!response.ok) {
    throw new Error(`Could not load storefront status (${response.status}).`);
  }
  const payload = await response.json();
  if (!["live", "maintenance"].includes(payload?.store_status)) {
    throw new Error("The storefront status service returned an invalid response.");
  }
  return payload;
}

function normalizeProduct(product, index) {
  if (!product || typeof product !== "object") {
    throw new Error(`Product at position ${index + 1} is not a valid object.`);
  }

  const image = product.image ?? product.image_url;
  const price = Number(product.price);
  if (
    (typeof product.id !== "string" && typeof product.id !== "number") ||
    !String(product.name ?? "").trim() ||
    !String(product.category ?? "").trim() ||
    !Number.isFinite(price) ||
    typeof image !== "string" ||
    !image.trim()
  ) {
    throw new Error(
      `Product at position ${index + 1} is missing a valid id, name, category, price, or image.`,
    );
  }

  const gallery = Array.isArray(product.gallery)
    ? product.gallery.filter((url) => typeof url === "string" && url.trim())
    : Array.isArray(product.images)
      ? product.images.filter((url) => typeof url === "string" && url.trim())
      : [];
  const category = String(product.category).trim();
  const normalizedCategory = category.toLowerCase();

  return {
    ...product,
    id: product.id,
    name: String(product.name).trim(),
    brand: String(product.brand ?? "Maison Muse"),
    detail: String(
      product.detail ??
        product.subtitle ??
        String(product.description ?? "").split(/(?<=[.!?])\s/, 1)[0],
    ),
    price,
    oldPrice:
      product.oldPrice !== null &&
      product.oldPrice !== undefined &&
      product.oldPrice !== "" &&
      Number.isFinite(Number(product.oldPrice))
        ? Number(product.oldPrice)
        : null,
    discount: String(product.discount ?? ""),
    category,
    rating:
      product.rating !== null &&
      product.rating !== undefined &&
      Number.isFinite(Number(product.rating))
        ? Number(product.rating)
        : null,
    tag: String(product.tag ?? "JUST FOR YOU"),
    tagColor: String(product.tagColor ?? ""),
    description: String(product.description ?? ""),
    details:
      product.details && typeof product.details === "object" && !Array.isArray(product.details)
        ? product.details
        : {},
    reviewsCount: Number.isFinite(Number(product.reviewsCount))
      ? Number(product.reviewsCount)
      : 0,
    inStock: product.inStock === undefined ? Number(product.stock ?? product.stock_quantity) > 0 : Boolean(product.inStock),
    stock: Number.isFinite(Number(product.stock ?? product.stock_quantity))
      ? Math.max(0, Number(product.stock ?? product.stock_quantity))
      : 0,
    image: image.trim(),
    gallery: gallery.length > 0 ? gallery : [image.trim()],
    nailSizes: Array.isArray(product.nailSizes ?? product.nail_sizes)
      ? product.nailSizes ?? product.nail_sizes
      : undefined,
    notes: Array.isArray(product.notes) ? product.notes : undefined,
    highlights: Array.isArray(product.highlights) ? product.highlights : undefined,
    tone: String(
      product.tone ??
        (normalizedCategory.includes("perfume")
          ? "rose"
          : normalizedCategory.includes("nail")
            ? "peach"
            : normalizedCategory.includes("skin")
              ? "cream"
              : "lilac"),
    ),
  };
}

export async function fetchProducts({
  search = "",
  category = "",
  deals = false,
  limit = 50,
  signal,
} = {}) {
  const params = new URLSearchParams();
  if (search.trim()) params.set("search", search.trim());
  if (category.trim()) params.set("category", category.trim());
  if (deals) params.set("deals", "true");
  if (limit !== 50) params.set("limit", String(limit));

  const query = params.toString();
  const endpoint = `${API_BASE_URL}/api/products${query ? `?${query}` : ""}`;
  let response;

  try {
    response = await fetch(endpoint, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Could not reach the products API. Check that the backend is running and the API URL is configured.",
    );
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) {
      throw new Error("The products API returned an invalid JSON response.");
    }
  }

  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(
        payload,
        `The products API request failed (${response.status}).`,
      ),
    );
  }

  const productList = Array.isArray(payload) ? payload : payload?.products;
  if (!Array.isArray(productList)) {
    throw new Error("The products API response must be an array or an object with a products array.");
  }

  return productList.map(normalizeProduct);
}

export async function fetchVerifiedSellers({
  search = "",
  category = "",
  sort = "popularity",
  limit = 24,
  offset = 0,
  signal,
} = {}) {
  const params = new URLSearchParams({
    search,
    category,
    sort,
    limit: String(limit),
    offset: String(offset),
  });
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/sellers/verified?${params}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the verified boutiques directory.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The verified boutiques API returned invalid JSON.");
  }
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, `The verified boutiques request failed (${response.status}).`),
    );
  }
  return payload;
}

export const fetchSellerInspection = (query) =>
  publicApiRequest(
    `/api/sellers/inspect?query=${encodeURIComponent(query)}`,
    "Could not reach the seller verification service.",
  );

export const fetchBuyerOrderTracking = (trackingId) =>
  publicApiRequest(
    `/api/orders/track/${encodeURIComponent(trackingId)}`,
    "Could not reach the order tracking service.",
  );

export async function fetchBuyerOrders() {
  let token = "";
  try {
    token =
      window.localStorage.getItem("mm-auth-token") ??
      window.localStorage.getItem("auth_token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  if (!token) throw new Error("Sign in to view orders placed with your account.");

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/orders/mine`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach your order history. Check that the backend is running.");
  }
  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The order history API returned invalid JSON.");
  }
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, `Could not load your orders (${response.status}).`),
    );
  }
  return payload;
}

export async function createOrder({ customer, items, signal }) {
  let token = "";
  try {
    token =
      window.localStorage.getItem("mm-auth-token") ??
      window.localStorage.getItem("auth_token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/orders`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        customer,
        items: items.map((item) => ({
          product_id: String(item.id),
          quantity: item.quantity,
          variant: item.variant ?? "",
        })),
      }),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Could not reach the orders API. Check that the backend is running and try again.",
    );
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) {
      throw new Error("The orders API returned an invalid JSON response.");
    }
  }

  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(
        payload,
        "The order could not be placed. Check product availability and try again.",
      ),
    );
  }

  if (
    typeof payload?.order_number !== "string" ||
    !payload.order_number ||
    typeof payload?.redirect_url !== "string"
  ) {
    throw new Error("The orders API response is missing Pesapal checkout details.");
  }

  return payload;
}

export async function createDemoCheckout({
  customer,
  items,
  city,
  deliveryNotes,
  mpesaPhone,
  signal,
}) {
  let token = "";
  try {
    token =
      window.localStorage.getItem("mm-auth-token") ??
      window.localStorage.getItem("auth_token") ??
      "";
  } catch {
    throw new Error("Your saved sign-in could not be accessed. Enable local storage and try again.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/orders/checkout`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        customer,
        items: items.map((item) => ({
          product_id: String(item.id),
          quantity: item.quantity,
          variant: item.variant ?? "",
        })),
        city,
        delivery_notes: deliveryNotes,
        mpesa_phone: mpesaPhone,
      }),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Could not reach the checkout API. Check that the backend is running and try again.",
    );
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The checkout API returned invalid JSON.");
  }
  if (!response.ok) {
    const checkoutError = new Error(
      getApiErrorMessage(
        payload,
        `Checkout could not be completed (${response.status}).`,
      ),
    );
    checkoutError.status = response.status;
    checkoutError.detail = payload?.detail;
    throw checkoutError;
  }
  return payload;
}

export async function verifyPesapalPayment({
  orderTrackingId,
  merchantReference,
  signal,
}) {
  const params = new URLSearchParams({
    order_tracking_id: orderTrackingId,
    merchant_reference: merchantReference,
  });
  let response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/payments/pesapal/status?${params}`,
      { headers: { Accept: "application/json" }, signal },
    );
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Could not reach the payment service to verify your Pesapal payment.");
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) throw new Error("The payment service returned an invalid response.");
  }
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, `Payment verification failed (${response.status}).`),
    );
  }
  return payload;
}

export async function subscribeToNewsletter(email, { signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/newsletter`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Could not reach the newsletter service. Please try again in a moment.",
    );
  }

  const responseText = await response.text();
  let payload;
  try {
    payload = responseText ? JSON.parse(responseText) : null;
  } catch {
    if (response.ok) {
      throw new Error("The newsletter service returned an invalid response.");
    }
  }

  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(payload, "We couldn’t save your signup. Please try again."),
    );
  }

  if (typeof payload?.message !== "string" || !payload.message) {
    throw new Error("The newsletter service returned an unexpected response.");
  }

  return payload;
}
