import { Link } from "react-router-dom";
import SellerInspectorModal from "../components/SellerInspectorModal.jsx";
import "./VerifySellerPage.css";

function VerifySellerPage() {
  return (
    <main className="verify-seller-page">
      <header className="verify-seller-page-header">
        <Link to="/" className="verify-seller-wordmark">maison <span>muse</span><i>.</i></Link>
        <Link to="/boutiques">Browse boutiques</Link>
      </header>
      <section className="verify-seller-intro">
        <span>BUY WITH CONFIDENCE</span>
        <h1>Know who you’re <em>shopping with.</em></h1>
        <p>Search official Maison Muse seller records and review verified fulfillment activity.</p>
      </section>
      <SellerInspectorModal embedded />
    </main>
  );
}

export default VerifySellerPage;
