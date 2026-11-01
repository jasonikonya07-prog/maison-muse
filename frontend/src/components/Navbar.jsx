import { ChevronDown, LogOut, UserRound } from "lucide-react";
import { Link } from "react-router-dom";

function Navbar({
  user,
  onOpenAuth,
  onBrowseWishlist,
  onLogout,
  onNotice,
  notice,
}) {
  const sellerSlug = user?.seller?.store_slug ?? user?.seller?.storeSlug;

  return (
    <details className="header-dropdown">
      <summary aria-label={user ? `Account menu for ${user.full_name}` : "Open account menu"}>
        <UserRound size={19} aria-hidden="true" />
        <span>{user ? user.full_name.split(/\s+/)[0] : "Sign In / Join"}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </summary>
      <div className="header-dropdown-panel">
        <strong>Your Maison Muse</strong>
        {!user ? (
          <>
            <button type="button" onClick={() => onOpenAuth("signin", "buyer")}>
              Sign In / Register
            </button>
            <button type="button" onClick={() => onOpenAuth("register", "seller")}>
              Become a Seller on Maison Muse
            </button>
            <Link to="/boutiques">Browse Verified Boutiques</Link>
            <Link to="/verify-seller">Seller Trust &amp; Verification</Link>
          </>
        ) : (
          <>
            <span className="account-menu-role">
              {user.role === "seller" ? "Beauty vendor" : user.role}
            </span>
            {user.role === "buyer" && (
              <>
                <Link to="/orders">My Orders &amp; Tracking</Link>
                <button type="button" onClick={onBrowseWishlist}>
                  Wishlist
                </button>
                <Link to="/boutiques">Browse Boutiques</Link>
              </>
            )}
            {user.role === "seller" && (
              <>
                <Link to="/seller">Seller Dashboard</Link>
                {sellerSlug && user.seller?.status === "APPROVED" && (
                  <Link to={`/boutiques/${encodeURIComponent(sellerSlug)}`}>
                    View My Public Storefront
                  </Link>
                )}
                <Link to="/seller#payouts">Payouts Ledger</Link>
              </>
            )}
            {user.role === "admin" && (
              <>
                <Link to="/admin">Admin Governance Console</Link>
                <Link to="/admin?section=vendors">Vendor Verification Queue</Link>
                <Link to="/admin?section=audit">System Audit Logs</Link>
              </>
            )}
            <Link to="/verify-seller">Seller Trust &amp; Verification</Link>
            {user.role !== "admin" && (
              <button type="button" onClick={onLogout}>
                <LogOut size={14} aria-hidden="true" /> Log Out
              </button>
            )}
          </>
        )}
        {notice && <p className="account-menu-notice" role="status">{notice}</p>}
      </div>
    </details>
  );
}

export default Navbar;
