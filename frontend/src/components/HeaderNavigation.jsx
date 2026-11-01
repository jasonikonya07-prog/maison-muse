import { ShieldCheck } from "lucide-react";

function HeaderNavigation({ onVerifySeller }) {
  return (
    <button
      type="button"
      className="header-action seller-verify-action"
      onClick={onVerifySeller}
      aria-label="Search vendors and verify a seller"
    >
      <span className="action-icon"><ShieldCheck size={19} strokeWidth={1.7} /></span>
      <span className="action-label">Verify Seller</span>
    </button>
  );
}

export default HeaderNavigation;
