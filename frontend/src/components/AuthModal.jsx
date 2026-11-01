import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  CreditCard,
  LoaderCircle,
  LockKeyhole,
  MapPin,
  Mail,
  Phone,
  ShoppingBag,
  Store,
  UserRound,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  loginAccount,
  loginWithGoogle,
  loginWithGoogleDemo,
  registerAccount,
} from "../services/api.js";
import {
  AGRICULTURE_BUSINESS_TYPE,
  AGRICULTURE_POLICY,
  BUSINESS_TYPES,
} from "../data/businessTypes.js";
import "./AuthModal.css";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? "";
const sellerPlans = [
  {
    id: "boutique",
    name: "Boutique Starter",
    price: "Free",
    commission: "10%",
    features: [
      "Up to 15 product listings",
      "Standard M-Pesa payouts",
    ],
  },
  {
    id: "pro",
    name: "Pro Studio",
    price: "KSh 2,500",
    featured: true,
    commission: "5%",
    features: [
      "Unlimited product listings",
      "Priority search placement",
      "Daily automatic payouts",
      "Custom store banner",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise Brand",
    price: "KSh 7,500",
    commission: "2.5%",
    features: [
      "Dedicated account manager",
      "API inventory sync",
      "Featured homepage placement",
    ],
  },
];

function AuthField({ icon: Icon, label, name, ...inputProps }) {
  const id = `auth-${name}`;
  return (
    <label className="auth-field" htmlFor={id}>
      <span>{label}</span>
      <span className="auth-field-control">
        <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
        <input id={id} name={name} {...inputProps} />
      </span>
    </label>
  );
}

function AuthModal({
  onClose,
  onAuthenticated,
  initialTab = "signin",
  initialRole = "buyer",
}) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(initialTab);
  const [role, setRole] = useState(initialRole);
  const [step, setStep] = useState(1);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [confirmedAuthenticity, setConfirmedAuthenticity] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState("boutique");
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    phone: "",
    store_name: "",
    business_category: BUSINESS_TYPES[1],
    business_type: BUSINESS_TYPES[1],
    whatsapp_number: "",
    city: "",
    payout_number: "",
    business_registration_number: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [googleReady, setGoogleReady] = useState(false);
  const googleToastTimer = useRef(null);
  const googleCredentialHandled = useRef(false);
  const modalRef = useRef(null);
  const onAuthenticatedRef = useRef(onAuthenticated);

  onAuthenticatedRef.current = onAuthenticated;

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  useEffect(() => {
    modalRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [activeTab, role, step]);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || role !== "buyer") {
      setGoogleReady(false);
      return undefined;
    }
    let active = true;
    let script = document.querySelector('script[data-maison-google-identity="true"]');

    const initializeGoogle = () => {
      if (!active || !window.google?.accounts?.id) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async ({ credential }) => {
          if (!credential || !active) return;
          googleCredentialHandled.current = true;
          setBusy(true);
          setError("");
          try {
            const result = await loginWithGoogle(credential);
            persistAuthentication(result);
          } catch (authError) {
            setError(authError.message);
          } finally {
            if (active) setBusy(false);
          }
        },
      });
      setGoogleReady(true);
    };

    if (!script) {
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.dataset.maisonGoogleIdentity = "true";
      script.addEventListener("load", initializeGoogle, { once: true });
      script.addEventListener(
        "error",
        () => {
          if (active) setError("Google sign-in could not be loaded. Please try again later.");
        },
        { once: true },
      );
      document.head.appendChild(script);
    } else if (window.google?.accounts?.id) {
      initializeGoogle();
    } else {
      script.addEventListener("load", initializeGoogle, { once: true });
    }

    return () => {
      active = false;
      script?.removeEventListener("load", initializeGoogle);
    };
  }, [role]);

  useEffect(
    () => () => window.clearTimeout(googleToastTimer.current),
    [],
  );

  const persistAuthentication = (result) => {
    const accessToken = result.access_token ?? result.token;
    if (!accessToken || !result.user) {
      setError("The authentication service returned an invalid response.");
      return;
    }
    try {
      window.localStorage.setItem("mm-auth-token", accessToken);
      window.localStorage.setItem("auth_token", accessToken);
      window.localStorage.setItem("mm-auth-user", JSON.stringify(result.user));
      window.localStorage.setItem("user_profile", JSON.stringify(result.user));
      window.localStorage.setItem(
        "mm-auth-expires-at",
        String(Date.now() + result.expires_in * 1000),
      );
    } catch {
      setError("Your sign-in could not be saved. Enable local storage and try again.");
      return;
    }
    onAuthenticatedRef.current(result.user);
    onClose();
    if (result.user.role === "seller") navigate("/seller");
  };

  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));

  const handleGoogleLogin = async () => {
    if (busy) return;
    setError("");
    setSuccess("");

    if (GOOGLE_CLIENT_ID) {
      if (!googleReady || !window.google?.accounts?.id) {
        setError("Google sign-in is still loading. Please try again in a moment.");
        return;
      }
      setBusy(true);
      googleCredentialHandled.current = false;
      window.google.accounts.id.prompt((notification) => {
        if (googleCredentialHandled.current) return;
        if (
          notification.isNotDisplayed?.() ||
          notification.isSkippedMoment?.() ||
          notification.isDismissedMoment?.()
        ) {
          setBusy(false);
          setError("Google sign-in was not completed. Please try again.");
        }
      });
      return;
    }

    if (!import.meta.env.DEV) {
      setError("Google sign-in is not configured for this environment.");
      return;
    }

    setBusy(true);
    try {
      const result = await loginWithGoogleDemo();
      setSuccess("Google Authentication Successful");
      googleToastTimer.current = window.setTimeout(
        () => persistAuthentication(result),
        1100,
      );
    } catch (authError) {
      setError(authError.message);
      setBusy(false);
    }
  };

  const switchTab = (nextTab) => {
    setActiveTab(nextTab);
    setStep(1);
    setError("");
    setAcceptedTerms(false);
    setConfirmedAuthenticity(false);
    setSelectedPlan("boutique");
  };

  const selectRole = (nextRole) => {
    setRole(nextRole);
    setStep(1);
    setError("");
    setAcceptedTerms(false);
    setConfirmedAuthenticity(false);
    setSelectedPlan("boutique");
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");

    if (activeTab === "register" && role === "seller") {
      if (step < 4) {
        setStep(step + 1);
        return;
      }
      if (!acceptedTerms || !confirmedAuthenticity) {
        setError("Accept the seller terms and confirm product authenticity to continue.");
        setStep(3);
        return;
      }
    }

    setBusy(true);
    try {
      const result =
        activeTab === "signin"
          ? await loginAccount(form.email, form.password)
          : await registerAccount({
              full_name: form.full_name,
              email: form.email,
              password: form.password,
              phone: form.phone,
              role,
              ...(role === "seller"
                ? {
                    store_name: form.store_name,
                    store_category: form.business_category,
                    business_type: form.business_type,
                    whatsapp_number: form.whatsapp_number,
                    city: form.city,
                    payout_number: form.payout_number,
                    national_id: form.business_registration_number,
                    accepted_terms: acceptedTerms && confirmedAuthenticity,
                    selected_plan: selectedPlan,
                  }
                : {}),
            });
      persistAuthentication(result);
    } catch (authError) {
      setError(authError.message);
    } finally {
      setBusy(false);
    }
  };

  const registration = activeTab === "register";
  const sellerRegistration = registration && role === "seller";
  const sellerBusinessStep = sellerRegistration && step === 2;
  const sellerTermsStep = sellerRegistration && step === 3;
  const sellerPlanStep = sellerRegistration && step === 4;
  const heroTitle = sellerRegistration
    ? step === 2
      ? <>Your brand, <em>beautifully.</em></>
      : step === 3
        ? <>Growing with <em>trust.</em></>
        : step === 4
          ? <>Your next <em>chapter.</em></>
          : <>Make your passion <em>your business.</em></>
    : registration
      ? <>Find a little more <em>you.</em></>
      : <>A little more <em>you.</em></>;
  const heroDescription = sellerRegistration
    ? step === 3
      ? "Clear, fair standards help keep our marketplace trustworthy for everyone."
      : step === 4
        ? "Choose the plan that fits your brand today. You can grow from here."
        : "Bring your beauty business to a community that loves discovering something new."
    : registration
      ? "Discover thoughtful beauty, fragrance, and little luxuries made for you."
      : "Welcome back. Your next favorite find is waiting.";

  return createPortal(
    <div
      className="auth-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className={`auth-modal ${sellerBusinessStep ? "is-business-step" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
      >
        <button
          className="auth-modal-close"
          type="button"
          aria-label="Close sign in"
          onClick={onClose}
        >
          <X size={19} />
        </button>
        <div className="auth-modal-grid grid grid-cols-1 md:grid-cols-12">
          <aside className="auth-hero-column md:col-span-5" aria-label="Maison Muse">
            <div
              className="auth-hero-image bg-cover bg-center transition-all duration-1000 transform hover:scale-110"
              style={{
                backgroundImage:
                  "url(https://images.unsplash.com/photo-1615634260167-c8cdede054de?auto=format&fit=crop&w=1400&q=90)",
              }}
              aria-hidden="true"
            />
            <div
              className="auth-hero-overlay bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent"
              aria-hidden="true"
            />
            <div className="auth-hero-badge" aria-hidden="true">
              <span className="auth-hero-badge-mark">✳</span>
              <span>MAISON MUSE</span>
            </div>
            <div className="auth-hero-copy">
              <span className="auth-hero-kicker">
                {registration && role === "seller"
                  ? "A HOME FOR BEAUTY ENTREPRENEURS"
                  : "BEAUTY, CURATED FOR YOU"}
              </span>
              <h2>{heroTitle}</h2>
              <p>{heroDescription}</p>
            </div>
          </aside>

          <div
            ref={modalRef}
            className="auth-form-column md:col-span-7"
          >
            <div className="auth-modal-content">
              <div className="auth-form-heading">
                <span className="auth-modal-eyebrow">
                  {sellerRegistration ? `SELLER ONBOARDING · STEP ${step} OF 4` : "WELCOME TO MAISON MUSE"}
                </span>
                <h2 id="auth-modal-title">
                  {sellerTermsStep
                    ? "Maison Muse Seller Terms of Service"
                    : sellerPlanStep
                      ? "Select Your Seller Plan"
                      : sellerBusinessStep
                        ? "Business profile"
                    : registration
                      ? "Create your account"
                      : "Sign in to your account"}
                </h2>
                <p className="auth-modal-intro">
                  {sellerTermsStep
                    ? "Review the marketplace agreement before choosing your seller plan."
                    : sellerPlanStep
                      ? "Select the subscription that best suits your business."
                      : sellerBusinessStep
                        ? "Tell us a little about your business to complete your seller application."
                    : registration
                      ? "A few details and you’ll be ready to explore."
                      : "Sign in to continue to your Maison Muse account."}
                </p>
              </div>

              {!sellerRegistration && (
                <div className="auth-modal-tabs" role="tablist" aria-label="Account access">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={!registration}
                    className={!registration ? "is-active" : ""}
                    onClick={() => switchTab("signin")}
                  >
                    Sign in
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={registration}
                    className={registration ? "is-active" : ""}
                    onClick={() => switchTab("register")}
                  >
                    Register
                  </button>
                </div>
              )}

              {sellerRegistration && (
                <div className="auth-onboarding-progress" aria-label={`Step ${step} of 4`}>
                  {["Personal details", "Business profile", "Agreement", "Plan"].map(
                    (label, index) => {
                      const stepNumber = index + 1;
                      return (
                        <div
                          className={`auth-onboarding-progress-step ${stepNumber < step ? "is-complete" : ""} ${stepNumber === step ? "is-current" : ""}`}
                          key={label}
                        >
                          <span className="auth-onboarding-progress-number">
                            {stepNumber < step ? <Check size={12} /> : stepNumber}
                          </span>
                          <span className="auth-onboarding-progress-label">{label}</span>
                        </div>
                      );
                    },
                  )}
                </div>
              )}

              <form className="auth-modal-form" onSubmit={submit}>
            {sellerTermsStep ? (
              <section className="auth-terms-panel" aria-labelledby="seller-terms-heading">
                <div className="auth-terms-box">
                  <h3 id="seller-terms-heading">Marketplace agreement</h3>
                  <p>
                    <strong>Commission and fees.</strong> Maison Muse retains the
                    commission shown for your selected plan from eligible completed
                    sales. Applicable fees are calculated transparently before
                    seller payouts.
                  </p>
                  <p>
                    <strong>Authenticity and quality.</strong> You are responsible
                    for listing safe, high-quality products and maintaining
                    authentic inventory. Counterfeit, imitation, or misleading
                    products are prohibited and may be removed.
                  </p>
                  <p>
                    <strong>M-Pesa payouts.</strong> You authorize automated M-Pesa
                    business-to-customer payouts to the account provided during
                    onboarding. Eligible proceeds are paid after delivery
                    confirmation and applicable fees or adjustments.
                  </p>
                  <p>
                    <strong>Returns and refunds.</strong> You agree to cooperate
                    with Maison Muse to resolve return, refund, and order disputes
                    under marketplace policies. Refunds may be deducted from
                    pending seller proceeds where applicable.
                  </p>
                  <p>
                    <strong>Payout schedules.</strong> Payout timing follows the
                    selected plan and may be subject to delivery confirmation,
                    payment processing, and account verification.
                  </p>
                </div>
                <label className="auth-terms-checkbox">
                  <input
                    type="checkbox"
                    checked={acceptedTerms}
                    onChange={(event) => setAcceptedTerms(event.target.checked)}
                  />
                  <span>I agree to Maison Muse Vendor Terms</span>
                </label>
                <label className="auth-terms-checkbox">
                  <input
                    type="checkbox"
                    checked={confirmedAuthenticity}
                    onChange={(event) => setConfirmedAuthenticity(event.target.checked)}
                  />
                  <span>I confirm all listed items are authentic</span>
                </label>
              </section>
            ) : sellerPlanStep ? (
              <section className="auth-plans-panel" aria-labelledby="seller-plans-heading">
                <h3 id="seller-plans-heading" className="auth-sr-only">
                  Choose a subscription plan
                </h3>
                <div className="auth-plan-grid" role="radiogroup" aria-label="Seller subscription plans">
                  {sellerPlans.map((plan) => (
                    <button
                      type="button"
                      role="radio"
                      aria-checked={selectedPlan === plan.id}
                      className={`auth-plan-card ${selectedPlan === plan.id ? "is-selected" : ""} ${plan.featured ? "is-featured" : ""}`}
                      key={plan.id}
                      onClick={() => setSelectedPlan(plan.id)}
                    >
                      {plan.featured && <span className="auth-plan-badge">Featured</span>}
                      <span className="auth-plan-radio" aria-hidden="true">
                        {selectedPlan === plan.id && <span />}
                      </span>
                      <strong className="auth-plan-name">{plan.name}</strong>
                      <span className="auth-plan-price">
                        {plan.price}<small> / month</small>
                      </span>
                      <span className="auth-plan-commission">
                        {plan.commission} platform commission
                      </span>
                      <ul>
                        {plan.features.map((feature) => (
                          <li key={feature}><Check size={13} /> {feature}</li>
                        ))}
                      </ul>
                    </button>
                  ))}
                </div>
              </section>
            ) : sellerBusinessStep ? (
              <div className="auth-business-fields">
                <AuthField
                  icon={Building2}
                  label="Store or brand name"
                  name="store-name"
                  type="text"
                  autoComplete="organization"
                  minLength="2"
                  maxLength="120"
                  required
                  value={form.store_name}
                  onChange={(event) => update("store_name", event.target.value)}
                />
                <label className="auth-field" htmlFor="auth-business-category">
                  <span>Primary Industry / Business Category</span>
                  <span className="auth-field-control">
                    <Store size={17} strokeWidth={1.7} aria-hidden="true" />
                    <select
                      id="auth-business-category"
                      name="business-category"
                      value={form.business_category}
                      onChange={(event) => {
                        update("business_category", event.target.value);
                        update("business_type", event.target.value);
                      }}
                      required
                    >
                      {BUSINESS_TYPES.map((businessType) => (
                        <option key={businessType} value={businessType}>
                          {businessType}
                        </option>
                      ))}
                    </select>
                  </span>
                </label>
                {form.business_type === AGRICULTURE_BUSINESS_TYPE && (
                  <>
                    <AuthField
                      icon={Phone}
                      label="Verified WhatsApp Business phone number"
                      name="whatsapp-number"
                      type="tel"
                      autoComplete="tel"
                      minLength="7"
                      maxLength="32"
                      required
                      value={form.whatsapp_number}
                      onChange={(event) => update("whatsapp_number", event.target.value)}
                    />
                    <p className="auth-agriculture-policy" role="note">
                      {AGRICULTURE_POLICY}
                    </p>
                  </>
                )}
                <AuthField
                  icon={MapPin}
                  label="City (optional)"
                  name="city"
                  type="text"
                  autoComplete="address-level2"
                  maxLength="100"
                  value={form.city}
                  onChange={(event) => update("city", event.target.value)}
                />
                <AuthField
                  icon={CreditCard}
                  label="M-Pesa number, Till, or Paybill"
                  name="payout-number"
                  type="text"
                  autoComplete="off"
                  minLength="3"
                  maxLength="120"
                  required
                  value={form.payout_number}
                  onChange={(event) => update("payout_number", event.target.value)}
                />
                <AuthField
                  icon={CreditCard}
                  label="National ID or business registration number"
                  name="business-registration-number"
                  type="text"
                  autoComplete="off"
                  minLength="3"
                  maxLength="100"
                  required
                  value={form.business_registration_number}
                  onChange={(event) =>
                    update("business_registration_number", event.target.value)
                  }
                />
                <p className="auth-privacy-note">
                  Your registration details are used only for seller verification.
                </p>
              </div>
            ) : (
              <>
                {registration && (
                  <>
                    <div className="auth-role-heading">
                      <span>Choose how you’ll use Maison Muse</span>
                    </div>
                    <div className="auth-role-cards" role="group" aria-label="Choose account type">
                      <button
                        type="button"
                        className={`auth-role-card ${role === "buyer" ? "is-selected" : ""}`}
                        aria-pressed={role === "buyer"}
                        onClick={() => selectRole("buyer")}
                      >
                        <span className="auth-role-icon"><ShoppingBag size={19} /></span>
                        <span className="auth-role-copy">
                          <strong>Shopper <span>(Buyer)</span></strong>
                          <small>Shop luxury edits</small>
                        </span>
                        {role === "buyer" && (
                          <CheckCircle2 className="auth-role-check" size={19} />
                        )}
                      </button>
                      <button
                        type="button"
                        className={`auth-role-card ${role === "seller" ? "is-selected" : ""}`}
                        aria-pressed={role === "seller"}
                        onClick={() => selectRole("seller")}
                      >
                        <span className="auth-role-icon"><Store size={19} /></span>
                        <span className="auth-role-copy">
                          <strong>Beauty Vendor <span>(Seller)</span></strong>
                          <small>Sell products &amp; earn</small>
                        </span>
                        {role === "seller" && (
                          <CheckCircle2 className="auth-role-check" size={19} />
                        )}
                      </button>
                    </div>
                    <div className="auth-personal-fields">
                      <AuthField
                        icon={UserRound}
                        label="Full name"
                        name="full-name"
                        type="text"
                        autoComplete="name"
                        minLength="4"
                        maxLength="120"
                        required
                        value={form.full_name}
                        onChange={(event) => update("full_name", event.target.value)}
                      />
                      <AuthField
                        icon={Mail}
                        label="Email address"
                        name="email"
                        type="email"
                        autoComplete="email"
                        maxLength="254"
                        required
                        value={form.email}
                        onChange={(event) => update("email", event.target.value)}
                      />
                      <AuthField
                        icon={Phone}
                        label="Phone number"
                        name="phone"
                        type="tel"
                        autoComplete="tel"
                        minLength="7"
                        maxLength="32"
                        required
                        value={form.phone}
                        onChange={(event) => update("phone", event.target.value)}
                      />
                      <AuthField
                        icon={LockKeyhole}
                        label="Password (12+ characters)"
                        name="password"
                        type="password"
                        autoComplete="new-password"
                        minLength="12"
                        maxLength="256"
                        required
                        value={form.password}
                        onChange={(event) => update("password", event.target.value)}
                      />
                    </div>
                  </>
                )}
                {!registration && (
                  <div className="auth-personal-fields auth-signin-fields">
                    <AuthField
                      icon={Mail}
                      label="Email address"
                      name="email"
                      type="email"
                      autoComplete="email"
                      maxLength="254"
                      required
                      value={form.email}
                      onChange={(event) => update("email", event.target.value)}
                    />
                    <AuthField
                      icon={LockKeyhole}
                      label="Password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      minLength="1"
                      maxLength="256"
                      required
                      value={form.password}
                      onChange={(event) => update("password", event.target.value)}
                    />
                  </div>
                )}
              </>
            )}

            {error && (
              <p className="auth-modal-error" role="alert">
                <span aria-hidden="true">!</span>{error}
              </p>
            )}
            {success && (
              <p className="auth-google-success" role="status">
                <CheckCircle2 size={16} aria-hidden="true" />
                {success}
              </p>
            )}

            {sellerRegistration && step > 1 ? (
              <div className="auth-step-actions">
                <button
                  className="auth-step-back"
                  type="button"
                  onClick={() => {
                    setStep((current) => current - 1);
                    setError("");
                  }}
                  disabled={busy}
                >
                  <ArrowLeft size={15} />
                  {step === 2
                    ? "Back to personal details"
                    : step === 3
                      ? "Back to business profile"
                      : "Back to agreement"}
                </button>
                <button
                  className="auth-modal-submit"
                  type="submit"
                  disabled={
                    busy ||
                    (sellerTermsStep && (!acceptedTerms || !confirmedAuthenticity))
                  }
                >
                  {busy ? (
                    <><LoaderCircle className="auth-spinner" size={16} /> Creating account…</>
                  ) : sellerTermsStep ? (
                    <>Next: Select Plan <ArrowRight size={16} aria-hidden="true" /></>
                  ) : sellerPlanStep ? (
                    <>Complete Onboarding &amp; Enter Portal <ArrowRight size={16} aria-hidden="true" /></>
                  ) : (
                    <>Next: Terms &amp; Agreement <ArrowRight size={16} aria-hidden="true" /></>
                  )}
                </button>
              </div>
            ) : (
              <button className="auth-modal-submit" type="submit" disabled={busy}>
                {busy ? (
                  <><LoaderCircle className="auth-spinner" size={16} /> Please wait…</>
                ) : sellerRegistration ? (
                    <>Continue to business profile <ArrowRight size={16} aria-hidden="true" /></>
                ) : registration ? (
                  <>Create account <ArrowRight size={16} aria-hidden="true" /></>
                ) : (
                  <>Sign in <ArrowRight size={16} aria-hidden="true" /></>
                )}
              </button>
            )}
              </form>

              {!sellerBusinessStep && (!registration || role === "buyer") && (
                <div className="auth-google-area">
                  <span className="auth-google-divider">or continue with</span>
                  <button
                    className="auth-google-button"
                    type="button"
                    onClick={handleGoogleLogin}
                    disabled={busy}
                  >
                    <svg
                      className="auth-google-logo"
                      viewBox="0 0 48 48"
                      aria-hidden="true"
                    >
                      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" />
                      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.93c-.58 2.96-2.26 5.48-4.76 7.18l7.73 6C44.4 37.97 46.98 31.9 46.98 24.55Z" />
                      <path fill="#FBBC05" d="M10.53 28.59A14.4 14.4 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.98-6.19A23.9 23.9 0 0 0 0 24c0 3.88.93 7.57 2.56 10.78l7.97-6.19Z" />
                      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.9-5.8l-7.73-6c-2.15 1.45-4.9 2.3-8.17 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z" />
                    </svg>
                    <span>Continue with Google</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}

export default AuthModal;
