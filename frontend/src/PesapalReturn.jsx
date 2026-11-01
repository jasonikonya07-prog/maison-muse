import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowRight, Check, LockKeyhole, RefreshCw } from "lucide-react";
import { verifyPesapalPayment } from "./services/api.js";

export default function PesapalReturn() {
  const [searchParams] = useSearchParams();
  const trackingId = searchParams.get("OrderTrackingId") ?? "";
  const merchantReference = searchParams.get("OrderMerchantReference") ?? "";
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  const verifyPayment = useCallback(async (signal) => {
    if (!trackingId || !merchantReference) {
      setError("The Pesapal return link is missing its payment reference.");
      return;
    }

    setChecking(true);
    setError("");
    try {
      const verified = await verifyPesapalPayment({
        orderTrackingId: trackingId,
        merchantReference,
        signal,
      });
      setResult(verified);
      if (verified.payment_status === "paid") {
        window.localStorage.removeItem("mm-cart-items");
      }
    } catch (verificationError) {
      if (verificationError.name !== "AbortError") {
        setError(verificationError.message);
      }
    } finally {
      if (!signal?.aborted) setChecking(false);
    }
  }, [merchantReference, trackingId]);

  useEffect(() => {
    const controller = new AbortController();
    verifyPayment(controller.signal);
    return () => controller.abort();
  }, [verifyPayment]);

  const paid = result?.payment_status === "paid";
  const failed = ["failed", "reversed"].includes(result?.payment_status);

  return (
    <main className="checkout-layer">
      <div className="checkout-page">
        <header className="checkout-header">
          <Link className="wordmark checkout-wordmark" to="/" aria-label="Maison Muse home">
            maison <span>muse</span><i aria-hidden="true">.</i>
          </Link>
          <div className="checkout-secure-note"><LockKeyhole size={14} /> Payment verification</div>
        </header>
        <section className="checkout-success" aria-live="polite">
          <span className="checkout-success-icon">
            {paid ? <Check size={24} /> : failed || error ? <AlertCircle size={24} /> : <RefreshCw size={22} />}
          </span>
          <div className="checkout-eyebrow">PESAPAL CHECKOUT</div>
          <h1>
            {paid ? <>Payment <em>confirmed.</em></> : failed ? <>Payment not <em>completed.</em></> : <>Checking your <em>payment.</em></>}
          </h1>
          <p className="checkout-success-copy">
            {paid
              ? "Pesapal confirmed your payment. Thank you for shopping with Maison Muse."
              : failed
                ? `Pesapal reported this payment as ${result.provider_status.toLowerCase()}. Your order has not been marked paid.`
                : error || "Your payment is not confirmed yet. Please wait a moment and check again before retrying."}
          </p>
          {merchantReference && (
            <div className="checkout-reference">
              <span>ORDER REFERENCE</span>
              <strong>{merchantReference}</strong>
            </div>
          )}
          {result?.payment_status && !paid && !failed && (
            <p className="checkout-confirmation-address">Payment status: <strong>{result.provider_status}</strong></p>
          )}
          {(!paid || error) && (
            <button
              className="checkout-submit"
              type="button"
              disabled={checking}
              onClick={() => verifyPayment()}
            >
              {checking ? "Checking with Pesapal…" : "Check payment status"}
              {!checking && <RefreshCw size={15} />}
            </button>
          )}
          <Link className="admin-back-store" to="/">
            {paid ? "Continue shopping" : "Return to Maison Muse"} <ArrowRight size={14} />
          </Link>
        </section>
      </div>
    </main>
  );
}
