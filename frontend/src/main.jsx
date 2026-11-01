import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import App from "./App.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";
import PesapalReturn from "./PesapalReturn.jsx";
import SellerDashboard from "./seller/SellerDashboard.jsx";
import StorePage from "./components/StorePage.jsx";
import VerifiedSellers from "./components/VerifiedSellers.jsx";
import BuyerOrderTracking from "./pages/BuyerOrderTracking.jsx";
import VerifySellerPage from "./pages/VerifySellerPage.jsx";
import { FeatureProvider } from "./context/FeatureContext.jsx";
import SupportWidget from "./components/SupportWidget.jsx";
import "./index.css";

function StorefrontSupportLayer() {
  const { pathname } = useLocation();
  if (
    pathname.startsWith("/admin") ||
    pathname.startsWith("/seller") ||
    pathname.startsWith("/checkout")
  ) {
    return null;
  }
  return <SupportWidget />;
}

function SellerRoleGuard() {
  let user = null;
  let expiresAt = null;
  try {
    user = JSON.parse(
      window.localStorage.getItem("user_profile") ??
        window.localStorage.getItem("mm-auth-user") ??
        "null",
    );
    expiresAt = window.localStorage.getItem("mm-auth-expires-at");
  } catch (error) {
    console.error("Unable to read the saved seller profile.", error);
  }
  const isExpired = expiresAt && Number(expiresAt) <= Date.now();
  if (user?.role && user.role !== "seller") {
    return <Navigate to="/?sellerLogin=1" replace />;
  }
  if (user?.role === "seller" && isExpired) {
    return <Navigate to="/?sellerLogin=1" replace />;
  }
  return <SellerDashboard />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <FeatureProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/checkout/pesapal-return" element={<PesapalReturn />} />
          <Route path="/orders" element={<BuyerOrderTracking />} />
          <Route path="/orders/:trackingId" element={<BuyerOrderTracking />} />
          <Route path="/verify-seller" element={<VerifySellerPage />} />
          <Route
            path="/agri-farm"
            element={<Navigate to="/shop?category=agriculture-livestock" replace />}
          />
          <Route path="/admin/*" element={<AdminDashboard />} />
          <Route path="/seller/*" element={<SellerRoleGuard />} />
          <Route path="/store/:sellerSlug" element={<StorePage />} />
          <Route path="/boutiques/:sellerSlug" element={<StorePage />} />
          <Route path="/boutiques" element={<VerifiedSellers directory />} />
          <Route path="*" element={<App />} />
        </Routes>
        <StorefrontSupportLayer />
      </BrowserRouter>
    </FeatureProvider>
  </React.StrictMode>,
);
