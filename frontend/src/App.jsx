import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { App as CapacitorApp } from "@capacitor/app";
import {
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "framer-motion";
import CheckoutModal from "./components/CheckoutModal.jsx";
import CategoryBar from "./components/CategoryBar.jsx";
import HeaderNavigation from "./components/HeaderNavigation.jsx";
import ProductModal from "./components/ProductModal.jsx";
import { FREE_SHIPPING_THRESHOLD } from "./Checkout.jsx";
import Footer from "./Footer.jsx";
import AuthModal from "./components/AuthModal.jsx";
import Navbar from "./components/Navbar.jsx";
import SellerInspectorModal from "./components/SellerInspectorModal.jsx";
import ProductSection from "./components/ProductSection.jsx";
import VerifiedSellers from "./components/VerifiedSellers.jsx";
import AgriFarmHub from "./pages/AgriFarmHub.jsx";
import { useFeatures } from "./context/FeatureContext.jsx";
import ShopPage from "./pages/ShopPage.jsx";
import { categoryPaths, categoryRoutes } from "./routes.js";
import { formatKsh } from "./data/currency.js";
import { CATALOG_CATEGORIES } from "./data/catalogCategories.js";
import useAndroidBackButton from "./hooks/useAndroidBackButton.js";
import {
  createDemoCheckout,
  fetchProducts,
  fetchStorefrontStatus,
  sellerLogout,
} from "./services/api.js";
import {
  ArrowRight,
  ChevronDown,
  Check,
  CircleHelp,
  Heart,
  MessageCircle,
  Minus,
  Menu,
  Pause,
  Plus,
  Play,
  Phone,
  Search,
  ShoppingBag,
  ShieldCheck,
  Sparkles,
  Store,
  Trash2,
  X,
} from "lucide-react";
import "./MaintenancePage.css";

const categories = [
  "All",
  ...CATALOG_CATEGORIES.map(({ name }) => name),
];

const categoryPageContent = {
  All: {
    eyebrow: "THE MAISON MUSE EDIT",
    title: <>All the good <em>stuff.</em></>,
    description: "Discover millions of verified products from top local and international sellers.",
  },
  "Perfumes & Fragrances": {
    eyebrow: "FIND YOUR SIGNATURE",
    title: <>Find your <em>fragrance.</em></>,
    description: "Discover perfumes and scents for every mood, moment, and version of you.",
  },
  "Press-On Nails": {
    eyebrow: "SALON AT HOME",
    title: <>Nails, your <em>way.</em></>,
    description: "Meet reusable press-on nail sets for a polished look, on your own time.",
  },
  "Skincare & Glow": {
    eyebrow: "YOUR SOFT RESET",
    title: <>Your skincare <em>ritual.</em></>,
    description: "Build a feel-good skincare routine with everyday essentials for your shelf.",
  },
  "Lip & Makeup Essentials": {
    eyebrow: "A LITTLE COLOR",
    title: <>Make room for <em>play.</em></>,
    description: "Find easy, feel-good lip and makeup essentials for the looks you love.",
  },
  "Hair & Accessories": {
    eyebrow: "THE FINISHING TOUCH",
    title: <>The little <em>extras.</em></>,
    description: "Thoughtful hair accessories and finishing touches for your everyday.",
  },
};

const navigationCategories = [
  { label: "Shop All", to: "/shop" },
  { label: "Official Stores", to: "/boutiques" },
  { label: "Electronics & Phones", to: "/shop?category=electronics,phones-accessories" },
  { label: "Fashion & Beauty", to: "/shop?category=fashion-clothing,beauty-cosmetics" },
  { label: "Home & Living", to: "/shop?category=home-furniture,kitchen-dining,lighting-electrical" },
  { label: "Groceries & Supermarket", to: "/shop?category=groceries-food" },
  { label: "Flash Sales & Deals", to: "/shop?deals=1" },
];

const heroSlides = [
  {
    id: "perfume",
    category: "Perfumes & Fragrances",
    tag: "THE SCENT EDIT",
    title: "A little more",
    emphasis: "you.",
    description: "Find the fragrance that feels like your favorite version of you.",
    image:
      "https://images.unsplash.com/photo-1615634260167-c8cdede054de?auto=format&fit=crop&w=1200&q=90",
    imageAlt: "Perfume bottles in a warm, sunlit still life",
    imagePosition: "center",
    filterCategory: "Perfumes & Fragrances",
  },
  {
    id: "skincare",
    category: "Skincare & Glow",
    tag: "YOUR SOFT RESET",
    title: "A ritual of",
    emphasis: "glow.",
    description: "Everyday skincare for the little moments that are all yours.",
    image:
      "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=1200&q=90",
    imageAlt: "Thoughtfully arranged skincare essentials",
    imagePosition: "center",
    filterCategory: "Skincare & Glow",
  },
  {
    id: "nails",
    category: "Press-On Nails",
    tag: "SALON AT HOME",
    title: "Your hands,",
    emphasis: "your rules.",
    description: "A fresh set, a little music, and a moment to yourself.",
    image:
      "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1200&q=90",
    imageAlt: "Glossy press-on nail set in soft light",
    imagePosition: "center",
    filterCategory: "Press-On Nails",
  },
  {
    id: "makeup",
    category: "Lip & Makeup Essentials",
    tag: "A LITTLE COLOR",
    title: "A touch of",
    emphasis: "glow.",
    description: "Easy, feel-good makeup for the looks you love.",
    image:
      "https://images.unsplash.com/photo-1617038220319-276d3cfab638?auto=format&fit=crop&w=1200&q=90",
    imageAlt: "Beauty essentials styled for an everyday look",
    imagePosition: "center",
    filterCategory: "Lip & Makeup Essentials",
  },
  {
    id: "accessories",
    category: "Hair & Accessories",
    tag: "THE FINISHING TOUCH",
    title: "Little things,",
    emphasis: "big mood.",
    description: "The finishing touches that make an everyday outfit your own.",
    image:
      "https://images.unsplash.com/photo-1617038220319-276d3cfab638?auto=format&fit=crop&w=1200&q=90",
    imageAlt: "Delicate accessories styled for an everyday look",
    imagePosition: "center",
    filterCategory: "Hair & Accessories",
  },
];

function getStoredAuthUser() {
  try {
    const stored =
      window.localStorage.getItem("user_profile") ??
      window.localStorage.getItem("mm-auth-user");
    const token =
      window.localStorage.getItem("auth_token") ??
      window.localStorage.getItem("mm-auth-token");
    const savedExpiry = window.localStorage.getItem("mm-auth-expires-at");
    const expiresAt = savedExpiry ? Number(savedExpiry) : null;
    if (
      !stored ||
      !token ||
      (expiresAt !== null && (!Number.isFinite(expiresAt) || expiresAt <= Date.now()))
    ) {
      return null;
    }
    const user = JSON.parse(stored);
    return user &&
      ["buyer", "seller", "admin"].includes(user.role) &&
      typeof user.full_name === "string" &&
      typeof user.email === "string"
      ? user
      : null;
  } catch (error) {
    console.error("Unable to read the saved account profile.", error);
    return null;
  }
}

function FlashSale({ onSelectCategory }) {
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const now = new Date();
    const nextReset = new Date(now);
    nextReset.setHours(24, 0, 0, 0);
    return Math.max(0, Math.floor((nextReset.getTime() - now.getTime()) / 1000));
  });

  useEffect(() => {
    const updateCountdown = () => {
      const now = new Date();
      const nextReset = new Date(now);
      nextReset.setHours(24, 0, 0, 0);
      setRemainingSeconds(
        Math.max(0, Math.floor((nextReset.getTime() - now.getTime()) / 1000)),
      );
    };

    updateCountdown();
    const intervalId = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  const hours = String(Math.floor(remainingSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((remainingSeconds % 3600) / 60)).padStart(2, "0");
  const seconds = String(remainingSeconds % 60).padStart(2, "0");

  return (
    <section className="flash-sale" aria-labelledby="flash-sale-heading">
      <div className="flash-sale-copy">
        <span className="flash-sale-eyebrow">
          <Sparkles size={13} aria-hidden="true" /> THE DAILY BEAUTY EDIT
        </span>
        <h2 id="flash-sale-heading">Flash Sale <em>spotlight</em></h2>
        <p>Find today’s feel-good picks before the edit resets.</p>
      </div>
      <div className="flash-sale-timer">
        <span className="flash-sale-timer-label">TODAY’S EDIT RESETS IN</span>
        <div
          className="flash-sale-clock"
          role="timer"
          aria-label={`${hours} hours, ${minutes} minutes, ${seconds} seconds`}
        >
          <span className="flash-sale-time-unit">
            <strong>{hours}</strong>
            <small>Hours</small>
          </span>
          <span className="flash-sale-time-separator" aria-hidden="true">:</span>
          <span className="flash-sale-time-unit">
            <strong>{minutes}</strong>
            <small>Minutes</small>
          </span>
          <span className="flash-sale-time-separator" aria-hidden="true">:</span>
          <span className="flash-sale-time-unit">
            <strong>{seconds}</strong>
            <small>Seconds</small>
          </span>
        </div>
      </div>
      <nav className="flash-sale-links" aria-label="Shop today’s beauty edit">
        <button type="button" onClick={() => onSelectCategory("Perfumes & Fragrances")}>Scent</button>
        <button type="button" onClick={() => onSelectCategory("Press-On Nails")}>Nails</button>
        <button type="button" onClick={() => onSelectCategory("Skincare & Glow")}>Skincare</button>
        <button type="button" onClick={() => onSelectCategory("Lip & Makeup Essentials")}>Makeup</button>
        <button type="button" onClick={() => onSelectCategory("Hair & Accessories")}>Accessories</button>
        <button
          className="flash-sale-shop-all"
          type="button"
          onClick={() => onSelectCategory("All")}
        >
          Explore the edit <ArrowRight size={15} aria-hidden="true" />
        </button>
      </nav>
    </section>
  );
}

function HeroCarousel({ onSelectCategory }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isAutoplayPaused, setIsAutoplayPaused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [hasFocus, setHasFocus] = useState(false);
  const reduceMotion = useReducedMotion();
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const smoothX = useSpring(pointerX, { stiffness: 180, damping: 22 });
  const smoothY = useSpring(pointerY, { stiffness: 180, damping: 22 });
  const rotateY = useTransform(smoothX, [-0.5, 0.5], [-8, 8]);
  const rotateX = useTransform(smoothY, [-0.5, 0.5], [6, -6]);
  const activeSlide = heroSlides[activeIndex];
  const slideCount = String(heroSlides.length).padStart(2, "0");
  const isPaused = isAutoplayPaused || isHovered || hasFocus || reduceMotion;

  useEffect(() => {
    if (isPaused) return undefined;
    const timerId = window.setTimeout(() => {
      setActiveIndex((current) => (current + 1) % heroSlides.length);
      pointerX.set(0);
      pointerY.set(0);
    }, 5200);
    return () => window.clearTimeout(timerId);
  }, [activeIndex, isPaused, pointerX, pointerY]);

  const goTo = (direction) => {
    setActiveIndex(
      (current) => (current + direction + heroSlides.length) % heroSlides.length,
    );
    pointerX.set(0);
    pointerY.set(0);
  };

  const handlePointerMove = (event) => {
    if (reduceMotion || event.pointerType === "touch") return;
    const bounds = event.currentTarget.getBoundingClientRect();
    pointerX.set((event.clientX - bounds.left) / bounds.width - 0.5);
    pointerY.set((event.clientY - bounds.top) / bounds.height - 0.5);
  };

  const resetPointer = () => {
    pointerX.set(0);
    pointerY.set(0);
  };

  return (
    <div
      className={`hero-visual hero-carousel ${isAutoplayPaused ? "is-autoplay-paused" : ""}`}
      role="region"
      aria-label="Featured beauty categories"
      aria-roledescription="carousel"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocusCapture={() => setHasFocus(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setHasFocus(false);
      }}
    >
      <motion.div
        className="hero-aura"
        aria-hidden="true"
        animate={reduceMotion ? {} : { scale: [1, 1.08, 1], opacity: [0.55, 0.85, 0.55] }}
        transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="hero-orbit hero-orbit-one" aria-hidden="true" />
      <div className="hero-orbit hero-orbit-two" aria-hidden="true" />

      <div className="hero-card-stage" onPointerLeave={resetPointer}>
        {heroSlides.map((slide, index) => {
          const offset = (index - activeIndex + heroSlides.length) % heroSlides.length;
          const isActive = offset === 0;
          const isNext = offset === 1;
          const isPrevious = offset === heroSlides.length - 1;
          const isVisible = isActive || isNext || isPrevious;

          return (
            <motion.div
              className="hero-card-slot"
              key={slide.id}
              initial={false}
              animate={
                isActive
                  ? { x: 0, scale: 1, rotateY: 0, opacity: 1, z: 50 }
                  : isNext
                    ? { x: "52%", y: 8, scale: 0.77, rotateY: -34, opacity: 0.82, z: -120 }
                    : isPrevious
                      ? { x: "-52%", y: 8, scale: 0.77, rotateY: 34, opacity: 0.82, z: -120 }
                      : { x: 0, scale: 0.68, rotateY: 0, opacity: 0, z: -220 }
              }
              transition={
                reduceMotion
                  ? { duration: 0.01 }
                  : {
                      x: { type: "spring", stiffness: 120, damping: 20 },
                      scale: { type: "spring", stiffness: 120, damping: 19 },
                      rotateY: { type: "spring", stiffness: 110, damping: 18 },
                      opacity: { duration: 0.35 },
                      z: { duration: 0.4 },
                    }
              }
              style={{
                zIndex: isActive ? 3 : isVisible ? 2 : 0,
                pointerEvents: isVisible ? "auto" : "none",
              }}
              aria-hidden={!isActive}
              role="group"
              aria-roledescription="slide"
              aria-label={`${index + 1} of ${heroSlides.length}: ${slide.category}`}
            >
              <motion.article
                className={`hero-feature-card ${isActive ? "is-active" : "is-side"}`}
                style={isActive && !reduceMotion ? { rotateX, rotateY } : undefined}
                onPointerMove={isActive ? handlePointerMove : undefined}
                onClick={() => {
                  if (isActive) return;
                  goTo(isNext ? 1 : -1);
                }}
                role={isActive ? undefined : "button"}
                tabIndex={isActive || !isVisible ? -1 : 0}
                onKeyDown={(event) => {
                  if (!isActive && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    goTo(isNext ? 1 : -1);
                  }
                }}
              >
                <img
                  className="hero-feature-image"
                  src={slide.image}
                  alt={slide.imageAlt}
                  style={{ objectPosition: slide.imagePosition }}
                  draggable="false"
                />
                <div className="hero-feature-shade" />
                <div className="hero-glass-panel">
                  <span className="hero-category-tag">
                    <Sparkles size={11} /> {slide.tag}
                  </span>
                  <span className="hero-glass-category">{slide.category}</span>
                  <h2>
                    {slide.title}
                    <br />
                    <em>{slide.emphasis}</em>
                  </h2>
                  <p>{slide.description}</p>
                  <button
                    className="hero-card-cta"
                    type="button"
                    tabIndex={isActive ? 0 : -1}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectCategory(slide.filterCategory);
                    }}
                  >
                    Explore the edit <ArrowRight size={14} />
                  </button>
                </div>
                  {isActive && (
                    <span
                      className="hero-card-number"
                      aria-label={`Slide ${String(index + 1).padStart(2, "0")} of ${slideCount}`}
                    >
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <i>/ {slideCount}</i>
                    </span>
                  )}
              </motion.article>
            </motion.div>
          );
        })}
      </div>

      <div className="hero-carousel-controls">
        <button
          type="button"
          className="hero-carousel-arrow"
          aria-label="Previous featured category"
          onClick={() => goTo(-1)}
        >
          <ArrowRight size={15} className="arrow-reverse" />
        </button>
        <div className="hero-carousel-dots" role="group" aria-label="Choose featured category">
          {heroSlides.map((slide, index) => (
            <button
              type="button"
              key={slide.id}
              className={`hero-carousel-dot ${index === activeIndex ? "is-active" : ""}`}
              aria-label={`Show ${slide.category}`}
              aria-pressed={index === activeIndex}
              title={`Show ${slide.category}`}
              onClick={() => {
                setActiveIndex(index);
                resetPointer();
              }}
            />
          ))}
        </div>
        <button
          type="button"
          className="hero-carousel-arrow"
          aria-label="Next featured category"
          onClick={() => goTo(1)}
        >
          <ArrowRight size={15} />
        </button>
        {!reduceMotion && (
          <button
            type="button"
            className="hero-carousel-arrow hero-autoplay-toggle"
            aria-label={isAutoplayPaused ? "Play automatic slides" : "Pause automatic slides"}
            aria-pressed={isAutoplayPaused}
            title={isAutoplayPaused ? "Play slides" : "Pause slides"}
            onClick={() => setIsAutoplayPaused((paused) => !paused)}
          >
            {isAutoplayPaused ? <Play size={12} /> : <Pause size={12} />}
          </button>
        )}
      </div>

      <div className="hero-carousel-caption" aria-live={isPaused ? "polite" : "off"}>
        <span className="hero-caption-mark" />
        <span>{activeSlide.category}</span>
      </div>
    </div>
  );
}

function ProductDetailModal({
  product,
  availableStock,
  onClose,
  onAddToCart,
  onBuyNow,
}) {
  const { verifiedSellerBadge } = useFeatures();
  const [activeImage, setActiveImage] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [selectedSize, setSelectedSize] = useState(
    product.nailSizes?.[2] ??
      (product.variants?.[0]
        ? `${product.variants[0].name}: ${product.variants[0].options[0]}`
        : ""),
  );
  const [addedToCart, setAddedToCart] = useState(false);
  const images = product.gallery ?? [product.image];
  const variantOptions = product.nailSizes?.length
    ? product.nailSizes
    : (product.variants ?? []).flatMap((variant) =>
        variant.options.map((option) => `${variant.name}: ${option}`),
      );
  const isInStock = availableStock > 0 && !product.seller?.holidayMode;

  const handleAddToCart = () => {
    onAddToCart(product, quantity, selectedSize);
    setAddedToCart(true);
  };

  return createPortal(
    <div className="product-modal-layer">
      <button
        className="product-modal-backdrop"
        type="button"
        aria-label={`Close ${product.name} details`}
        onClick={onClose}
      />
      <section
        className="product-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-modal-title"
      >
        <button
          className="product-modal-close"
          type="button"
          aria-label="Close product details"
          onClick={onClose}
          autoFocus
        >
          <X size={19} />
        </button>

        <div className="product-modal-gallery">
          <div className="product-modal-image">
            <img src={images[activeImage]} alt={`${product.name} preview ${activeImage + 1}`} />
            <span className={`stock-badge ${isInStock ? "is-available" : "is-sold-out"}`}>
              <span />
              {isInStock
                ? availableStock <= 5
                  ? `Only ${availableStock} left`
                  : "In stock"
                : "Sold out"}
            </span>
          </div>
          <div className="product-thumbnails" aria-label="Product image previews">
            {images.map((image, index) => (
              <button
                className={`product-thumbnail ${activeImage === index ? "is-active" : ""}`}
                type="button"
                key={`${product.id}-${index}`}
                aria-label={`Show ${product.name} image ${index + 1}`}
                aria-pressed={activeImage === index}
                onClick={() => setActiveImage(index)}
              >
                <img src={image} alt="" />
              </button>
            ))}
          </div>
        </div>

        <div className="product-modal-details">
          <div className="product-modal-category">{product.category}</div>
          <h2 id="product-modal-title">{product.name}</h2>
          <p className="product-modal-subtitle">{product.detail}</p>
          {product.seller?.storeName && (
            <>
              <Link
                className="product-seller-attribution modal-seller-attribution"
                to={`/boutiques/${encodeURIComponent(product.seller.storeSlug)}`}
                onClick={onClose}
              >
                Sold &amp; fulfilled by {product.seller.storeName}
                {verifiedSellerBadge && product.seller.verified !== false && (
                  <ShieldCheck
                    className="product-seller-verified"
                    size={14}
                    aria-label="Verified seller"
                  />
                )}
              </Link>
              {(product.seller.businessPhone || product.seller.whatsappPhone) && (
                <p className="product-seller-contact modal-seller-contact">
                  <Phone size={13} aria-hidden="true" />
                  Support / WhatsApp:
                  <a
                    href={`tel:${(product.seller.businessPhone || product.seller.whatsappPhone).replace(/[^\d+]/g, "")}`}
                    onClick={onClose}
                  >
                    {product.seller.businessPhone || product.seller.whatsappPhone}
                  </a>
                  <a
                    href={`https://wa.me/${(product.seller.whatsappPhone || product.seller.businessPhone).replace(/\D/g, "").replace(/^0/, "254")}`}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Chat with ${product.seller.storeName} on WhatsApp`}
                    onClick={onClose}
                  >
                    <MessageCircle size={15} />
                  </a>
                </p>
              )}
              {product.seller.holidayMode && (
                <p className="product-seller-holiday">This boutique is on holiday pause and is not accepting orders.</p>
              )}
            </>
          )}
          {product.rating !== null && (
            <div className="modal-rating">
              <span aria-label={`${product.rating} out of 5 stars`}>★★★★★</span>
              <strong>{product.rating.toFixed(1)}</strong>
              <span className="modal-review-copy">A favorite around here</span>
            </div>
          )}
          <div className="product-modal-price">{formatKsh(product.price)}</div>
          <p className="product-modal-description">{product.description}</p>

          {product.details && Object.keys(product.details).length > 0 && (
            <div className="product-feature-block">
              <h3>Product details</h3>
              <div className="fragrance-notes">
                {Object.entries(product.details)
                  .filter(([key]) => key !== "availableSizes")
                  .map(([key, value]) => (
                  <div className="fragrance-note" key={key}>
                    <span>{key.replace(/([A-Z])/g, " $1")}</span>
                    <strong>{Array.isArray(value) ? value.join(", ") : value}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}

          {variantOptions.length > 0 && (
            <fieldset className="nail-size-picker">
              <legend>
                Choose an option
              </legend>
              <div className="nail-size-options">
                {variantOptions.map((size) => (
                  <button
                    className={selectedSize === size ? "is-selected" : ""}
                    type="button"
                    key={size}
                    aria-pressed={selectedSize === size}
                    onClick={() => setSelectedSize(size)}
                  >
                    {size}
                  </button>
                ))}
              </div>
              <span className="size-help">Not sure? Medium fits most.</span>
            </fieldset>
          )}

          <div className="modal-purchase">
            <div className="modal-quantity-picker" aria-label="Quantity">
              <button
                type="button"
                aria-label="Decrease quantity"
                disabled={quantity <= 1}
                onClick={() => setQuantity((current) => Math.max(1, current - 1))}
              >
                <Minus size={14} />
              </button>
              <span aria-live="polite">{quantity}</span>
              <button
                type="button"
                aria-label="Increase quantity"
                disabled={quantity >= availableStock}
                onClick={() =>
                  setQuantity((current) => Math.min(availableStock, current + 1))
                }
              >
                <Plus size={14} />
              </button>
            </div>
            <span className="modal-line-price">{formatKsh(product.price * quantity)}</span>
          </div>

          <div className="product-modal-actions">
            <button
              className="modal-add-button"
              type="button"
              disabled={!isInStock}
              onClick={handleAddToCart}
            >
              <ShoppingBag size={16} />
              {isInStock ? "Add to Cart" : "Sold Out"}
              <span>{formatKsh(product.price * quantity)}</span>
            </button>
            <button
              className="modal-buy-button"
              type="button"
              disabled={!isInStock}
              onClick={() => onBuyNow(product, quantity, selectedSize)}
            >
              Buy Now <ArrowRight size={16} />
            </button>
          </div>
          {addedToCart && (
            <p className="modal-added-message" role="status">
              <Check size={14} /> Added to your bag. Lovely choice.
            </p>
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}

function Counter({ children, label }) {
  return (
    <span className="counter" aria-label={`${children} ${label}`}>
      {children}
    </span>
  );
}

function App() {
  const { agriFarmHub } = useFeatures();
  const location = useLocation();
  const navigate = useNavigate();
  const activeCategory = categoryRoutes[location.pathname] ?? "All";
  const searchParams = new URLSearchParams(location.search);
  const queryCategorySlug = searchParams.get("category") ?? "";
  const dealsOnly = searchParams.get("deals") === "1";
  const selectedCatalogCategory = CATALOG_CATEGORIES.find(
    (category) => category.slug === queryCategorySlug,
  );
  const selectedNavigationCategory = navigationCategories.find(
    (category) => category.to.endsWith(`category=${queryCategorySlug}`),
  );
  const displayCategory = dealsOnly
    ? "Flash Sales & Deals"
    : selectedNavigationCategory?.label ?? selectedCatalogCategory?.name ?? activeCategory;
  const isShopPage = location.pathname !== "/";
  const isKnownRoute = location.pathname === "/" || location.pathname in categoryRoutes;
  const [search, setSearch] = useState("");
  const [products, setProducts] = useState([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState("");
  const [productsRetry, setProductsRetry] = useState(0);
  const [storefrontStatus, setStorefrontStatus] = useState("checking");
  const [storefrontStatusError, setStorefrontStatusError] = useState("");
  const [authUser, setAuthUser] = useState(getStoredAuthUser);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authInitialTab, setAuthInitialTab] = useState("signin");
  const [authInitialRole, setAuthInitialRole] = useState("buyer");
  const [authNotice, setAuthNotice] = useState("");
  const [sellerInspectorOpen, setSellerInspectorOpen] = useState(false);
  const [wishlist, setWishlist] = useState([]);
  const [showWishlist, setShowWishlist] = useState(false);
  const [cartItems, setCartItems] = useState(() => {
    try {
      const savedCart = window.localStorage.getItem("mm-cart-items");
      return savedCart ? JSON.parse(savedCart) : [];
    } catch {
      return [];
    }
  });
  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [checkoutMessage, setCheckoutMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const cartCount = useMemo(
    () => cartItems.reduce((total, item) => total + item.quantity, 0),
    [cartItems],
  );
  const cartTotal = useMemo(
    () => cartItems.reduce((total, item) => total + item.price * item.quantity, 0),
    [cartItems],
  );

  useEffect(() => {
    try {
      window.localStorage.setItem("mm-cart-items", JSON.stringify(cartItems));
    } catch (error) {
      console.error("Unable to persist the shopping cart.", error);
    }
  }, [cartItems]);

  useEffect(() => {
    if (!isKnownRoute) return;

    window.scrollTo(0, 0);
    document.title =
      location.pathname === "/"
        ? "Maison Muse — Beauty, made personal"
        : `${displayCategory === "All" ? "Shop all" : displayCategory} | Maison Muse`;
    const description = document.querySelector('meta[name="description"]');
    if (description) {
      description.content =
        location.pathname === "/"
          ? "Discover millions of verified products from top local and international sellers."
          : selectedCatalogCategory
            ? `Browse verified products in ${selectedCatalogCategory.name}.`
            : selectedNavigationCategory
              ? `Explore verified products across ${selectedNavigationCategory.label}.`
            : categoryPageContent[activeCategory].description;
    }
  }, [
    activeCategory,
    displayCategory,
    isKnownRoute,
    location.pathname,
    navigate,
    selectedNavigationCategory,
    selectedCatalogCategory,
  ]);

  useEffect(() => {
    const controller = new AbortController();
    setProductsLoading(true);
    setProductsError("");

    const timeoutId = window.setTimeout(() => {
      fetchProducts({
        search,
        category: queryCategorySlug || (activeCategory === "All" ? "" : activeCategory),
        deals: dealsOnly,
        signal: controller.signal,
      })
        .then(setProducts)
        .catch((error) => {
          if (error.name !== "AbortError") {
            setProducts([]);
            setProductsError(error.message);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setProductsLoading(false);
        });
    }, search.trim() ? 250 : 0);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [activeCategory, dealsOnly, productsRetry, queryCategorySlug, search, selectedCatalogCategory?.slug]);

  useEffect(() => {
    let active = true;
    const refreshStatus = () => {
      fetchStorefrontStatus()
        .then(({ store_status }) => {
          if (!active) return;
          setStorefrontStatus(store_status);
          setStorefrontStatusError("");
        })
        .catch((error) => {
          if (active) {
            setStorefrontStatusError(error.message);
            setStorefrontStatus((current) =>
              current === "checking" ? "live" : current,
            );
          }
        });
    };

    refreshStatus();
    const intervalId = window.setInterval(refreshStatus, 15000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (!cartOpen && !checkoutOpen && !selectedProduct) return undefined;

    const closeOnEscape = (event) => {
      if (event.key === "Escape") {
        if (selectedProduct) {
          setSelectedProduct(null);
        } else if (checkoutOpen) {
          setCheckoutOpen(false);
          setCartOpen(true);
        } else {
          setCartOpen(false);
        }
      }
    };

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [cartOpen, checkoutOpen, selectedProduct]);

  const handleAndroidBackButton = useCallback(({ canGoBack }) => {
    if (checkoutOpen) {
      setCheckoutOpen(false);
      setCartOpen(true);
    } else if (selectedProduct) {
      setSelectedProduct(null);
    } else if (cartOpen) {
      setCartOpen(false);
    } else if (menuOpen) {
      setMenuOpen(false);
    } else if (canGoBack) {
      navigate(-1);
    } else {
      void CapacitorApp.exitApp().catch((error) => {
        console.error("Unable to exit the Android app.", error);
      });
    }
  }, [cartOpen, checkoutOpen, menuOpen, navigate, selectedProduct]);
  useAndroidBackButton(handleAndroidBackButton);

  const visibleProducts = useMemo(() => {
    return showWishlist
      ? products.filter((product) => wishlist.includes(product.id))
      : products;
  }, [products, showWishlist, wishlist]);

  const toggleWishlist = (id) => {
    setWishlist((current) =>
      current.includes(id)
        ? current.filter((productId) => productId !== id)
        : [...current, id],
    );
  };

  const addToCart = (product, quantity = 1, variant = "") => {
    if (product.is_agri_product) return;
    setCheckoutMessage("");
    setCartItems((current) => {
      const cartKey = `${product.id}-${variant || "default"}`;
      const currentProductQuantity = current
        .filter((item) => item.id === product.id)
        .reduce((total, item) => total + item.quantity, 0);
      const quantityToAdd = Math.min(
        quantity,
        Math.max(0, product.stock - currentProductQuantity),
      );
      if (quantityToAdd === 0) return current;

      const existing = current.find((item) => item.cartKey === cartKey);
      if (existing) {
        return current.map((item) =>
          item.cartKey === cartKey
            ? { ...item, quantity: item.quantity + quantityToAdd }
            : item,
        );
      }
      return [...current, { ...product, cartKey, variant, quantity: quantityToAdd }];
    });
  };

  const changeCartQuantity = (cartKey, change) => {
    setCheckoutMessage("");
    setCartItems((current) => {
      const itemToChange = current.find((item) => item.cartKey === cartKey);
      if (!itemToChange) return current;
      const productQuantity = current
        .filter((item) => item.id === itemToChange.id)
        .reduce((total, item) => total + item.quantity, 0);
      if (change > 0 && productQuantity >= itemToChange.stock) return current;

      return current
        .map((item) =>
          item.cartKey === cartKey
            ? { ...item, quantity: item.quantity + change }
            : item,
        )
        .filter((item) => item.quantity > 0);
    });
  };

  const getAvailableStock = (product) =>
    Math.max(
      0,
      product.stock -
        cartItems
          .filter((item) => item.id === product.id)
          .reduce((total, item) => total + item.quantity, 0),
    );

  const buyNow = (product, quantity, variant) => {
    addToCart(product, quantity, variant);
    setSelectedProduct(null);
    setCartOpen(true);
  };

  const browseProducts = () => {
    setShowWishlist(false);
    setSearch("");
    navigate("/shop");
  };

  const browseCategory = (category) => {
    setSearch("");
    setShowWishlist(false);
    setMenuOpen(false);
    navigate(categoryPaths[category] ?? "/shop");
  };

  const browseCatalogCategory = (slug) => {
    setShowWishlist(false);
    setSearch("");
    setMenuOpen(false);
    navigate(slug ? `/shop?category=${encodeURIComponent(slug)}` : "/shop");
  };

  const browseMarketplaceNavigation = (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    setShowWishlist(false);
    setSearch("");
    setMenuOpen(false);
  };

  const selectCatalogCategory = (slug) => {
    browseCatalogCategory(slug);
  };

  const submitSearch = (event) => {
    event.preventDefault();
    setShowWishlist(false);
    navigate("/shop");
  };

  const openWishlist = () => {
    setShowWishlist(true);
    setSearch("");
    navigate("/shop");
  };

  const toggleWishlistView = () => {
    setShowWishlist((showing) => !showing);
    setSearch("");
    navigate("/shop");
  };

  const closeAuthModal = useCallback(() => setAuthModalOpen(false), []);
  const openAuthModal = useCallback((tab = "signin", role = "buyer") => {
    setAuthInitialTab(tab);
    setAuthInitialRole(role);
    setAuthModalOpen(true);
  }, []);
  useEffect(() => {
    if (new URLSearchParams(location.search).get("sellerLogin") !== "1") return;
    openAuthModal("signin", "seller");
    navigate("/", { replace: true });
  }, [location.search, navigate, openAuthModal]);
  const acceptAuthenticatedUser = useCallback((user) => {
    setAuthUser(user);
    setAuthNotice("");
  }, []);
  const logoutAccount = async () => {
    if (authUser?.role === "seller") {
      try {
        await sellerLogout();
      } catch (error) {
        console.error("Unable to revoke the legacy seller session.", error);
      }
    }
    try {
      window.localStorage.removeItem("mm-auth-token");
      window.localStorage.removeItem("auth_token");
      window.localStorage.removeItem("mm-auth-user");
      window.localStorage.removeItem("user_profile");
      window.localStorage.removeItem("mm-auth-expires-at");
      setAuthUser(null);
      setAuthNotice("");
    } catch (error) {
      console.error("Unable to clear the saved sign-in.", error);
      setAuthNotice("Your saved sign-in could not be cleared. Please enable local storage.");
    }
  };

  const productSectionProps = {
    loading: productsLoading,
    error: productsError,
    onRetry: () => setProductsRetry((attempt) => attempt + 1),
    wishlist,
    onToggleWishlist: toggleWishlist,
    onAddToCart: addToCart,
    onSelectProduct: setSelectedProduct,
    getAvailableStock,
    search,
    onSearchChange: setSearch,
    showWishlist,
    onBrowseAll: () => {
      setShowWishlist(false);
      setSearch("");
      navigate("/shop");
    },
  };

  if (!isKnownRoute) return <Navigate to="/" replace />;

  if (storefrontStatus === "checking") {
    return (
      <main className="store-maintenance-screen">
        <Link className="store-maintenance-brand" to="/">maison <span>muse.</span></Link>
        <span className="store-maintenance-eyebrow">A MOMENT, PLEASE</span>
        <p>We’re getting your Maison Muse experience ready.</p>
      </main>
    );
  }

  if (storefrontStatus === "maintenance") {
    return (
      <main className="store-maintenance-screen">
        <Link className="store-maintenance-brand" to="/">maison <span>muse.</span></Link>
        <span className="store-maintenance-eyebrow">A LITTLE BEAUTY BREAK</span>
        <h1>We’ll be back <em>shortly.</em></h1>
        <p>Maison Muse is having a moment behind the scenes. We’re refreshing the store and will be back soon.</p>
        {storefrontStatusError && (
          <p className="store-maintenance-note" role="status">
            Store availability could not be refreshed. Please try again in a moment.
          </p>
        )}
        <Link className="store-maintenance-admin" to="/admin">Store team sign in <ArrowRight size={15} /></Link>
      </main>
    );
  }

  return (
    <div className="site-shell">
      {storefrontStatusError && (
        <div className="store-status-warning" role="status">
          Store availability could not be confirmed. Some store services may be unavailable.
        </div>
      )}
      <div className="utility-bar">
        <Link className="utility-official-store" to="/shop">
          <Store size={14} aria-hidden="true" />
          <span>OFFICIAL MAISON MUSE STORE</span>
        </Link>
        <div className="utility-bar-links">
          <span>Beauty, made personal</span>
          <a href="#trust-and-care">Delivery &amp; returns</a>
          <a href="#newsletter">Contact us</a>
          <Link className="utility-track-order" to="/orders">
            Track your order
          </Link>
        </div>
      </div>

      <header className="site-header">
        <div className="header-inner">
          <button
            className="icon-button mobile-menu-button"
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>

          <Link className="wordmark" to="/" aria-label="Maison Muse home">
            maison <span>muse</span>
            <i aria-hidden="true">.</i>
          </Link>

          <form className="search-wrap" role="search" onSubmit={submitSearch}>
            <input
              type="search"
              placeholder="Search products, brands, or boutique sellers..."
              aria-label="Search products"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="submit" className="search-submit">
              <Search size={17} strokeWidth={2} aria-hidden="true" />
              <span>Search</span>
            </button>
          </form>

          <div className="header-actions">
            <Navbar
              user={authUser}
              onOpenAuth={openAuthModal}
              onBrowseWishlist={openWishlist}
              onLogout={logoutAccount}
              onNotice={setAuthNotice}
              notice={authNotice}
            />
            <HeaderNavigation onVerifySeller={() => setSellerInspectorOpen(true)} />
            <details className="header-dropdown">
              <summary aria-label="Open help menu">
                <CircleHelp size={19} aria-hidden="true" />
                <span>Help</span>
                <ChevronDown size={13} aria-hidden="true" />
              </summary>
              <div className="header-dropdown-panel">
                <strong>How can we help?</strong>
                <a href="#trust-and-care">Delivery &amp; returns</a>
                <a href="#newsletter">Contact &amp; updates</a>
                <p>Payments are completed securely through Pesapal.</p>
              </div>
            </details>
            <button
              className="header-action wishlist-action"
              type="button"
              aria-label={`Wishlist, ${wishlist.length} ${
                wishlist.length === 1 ? "item" : "items"
              }`}
              aria-pressed={showWishlist}
              onClick={toggleWishlistView}
            >
              <span className="action-icon">
                <Heart size={19} strokeWidth={1.65} />
                <Counter
                  label={`${wishlist.length === 1 ? "item" : "items"} in wishlist`}
                >
                  {wishlist.length}
                </Counter>
              </span>
              <span className="action-label">Wishlist</span>
            </button>
            <button
              className="header-action"
              type="button"
              aria-label={`Shopping bag, ${cartCount} ${
                cartCount === 1 ? "item" : "items"
              }`}
              aria-expanded={cartOpen}
              aria-controls="cart-drawer"
              onClick={() => setCartOpen(true)}
            >
              <span className="action-icon">
                <ShoppingBag size={19} strokeWidth={1.65} />
                <Counter label={`${cartCount === 1 ? "item" : "items"} in bag`}>
                  {cartCount}
                </Counter>
              </span>
              <span className="action-label">Bag</span>
            </button>
          </div>
        </div>

        <nav className={`main-nav ${menuOpen ? "is-open" : ""}`}>
          {navigationCategories.map(({ label, to }) => {
            const active = to === "/boutiques"
              ? location.pathname === "/boutiques"
              : to === "/shop"
                ? isShopPage && !queryCategorySlug && !dealsOnly
                : to.includes("deals=1")
                  ? dealsOnly
                  : queryCategorySlug && to.endsWith(`category=${queryCategorySlug}`);
            return (
              <Link
                to={to}
                key={label}
                aria-current={active ? "page" : undefined}
                onClick={browseMarketplaceNavigation}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <CategoryBar
          activeSlug={selectedCatalogCategory?.slug ?? ""}
          onSelectCategory={selectCatalogCategory}
        />
      </header>

      <SellerInspectorModal
        isOpen={sellerInspectorOpen}
        onClose={() => setSellerInspectorOpen(false)}
      />

      <main>
        {!isShopPage && <section className="hero" aria-labelledby="hero-heading">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-line" />
              MAISON MUSE · BEAUTY STARTS HERE
            </div>
            <h1 id="hero-heading">
              Your next
              <br />
              beauty <em>obsession.</em>
            </h1>
            <p className="hero-description">
              Discover millions of verified products from top local and international sellers.
            </p>
            <button className="primary-button" type="button" onClick={browseProducts}>
              SHOP THE EDIT
              <ArrowRight size={16} strokeWidth={1.8} />
            </button>
            <div className="hero-footnote">
              <span className="hero-assurance-dot" />
              <span>Little luxuries. Big main-character energy.</span>
            </div>
          </div>

          <HeroCarousel onSelectCategory={browseCategory} />
        </section>}

        {!isShopPage && <FlashSale onSelectCategory={browseCategory} />}
        {!isShopPage && <VerifiedSellers />}

        <section
          className={`shop-section ${isShopPage ? "category-shop-section" : ""}`}
          id="shop"
          aria-labelledby="shop-heading"
        >
          {isShopPage && (
            <nav className="shop-breadcrumb" aria-label="Breadcrumb">
              <Link to="/">Home</Link>
              <span aria-hidden="true">/</span>
              <span aria-current="page">
                {displayCategory === "All" ? "Shop all" : displayCategory}
              </span>
            </nav>
          )}
          <div className="shop-heading-row">
            <div>
              <div className="eyebrow shop-eyebrow">
                <span className="eyebrow-line" />
                {isShopPage
                  ? selectedCatalogCategory
                    || selectedNavigationCategory
                    || dealsOnly
                    ? "VERIFIED MULTI-VENDOR CATALOG"
                    : categoryPageContent[activeCategory].eyebrow
                  : "YOUR NEXT LITTLE OBSESSION"}
              </div>
              {isShopPage ? (
                <h1 className="category-page-title" id="shop-heading">
                  {showWishlist
                    ? <>Saved for <em>later.</em></>
                    : selectedCatalogCategory
                      ? <>Shop <em>{selectedCatalogCategory.name}.</em></>
                      : selectedNavigationCategory || dealsOnly
                        ? <>Shop <em>{displayCategory}.</em></>
                      : categoryPageContent[activeCategory].title}
                </h1>
              ) : (
                <h2 id="shop-heading">
                {showWishlist ? (
                  <>Saved for <em>later.</em></>
                ) : (
                  categoryPageContent[activeCategory].title
                )}
                </h2>
              )}
              {isShopPage && !showWishlist && (
                <p className="category-page-description">
                  {selectedCatalogCategory
                    ? `Explore verified products across ${selectedCatalogCategory.name}.`
                    : selectedNavigationCategory || dealsOnly
                      ? `Explore verified products across ${displayCategory}.`
                      : categoryPageContent[activeCategory].description}
                </p>
              )}
            </div>
            <Link className="view-all-link" to="/shop">
              Browse everything <ArrowRight size={15} />
            </Link>
          </div>

          <nav className="category-row" aria-label="Shop by category">
            {categories.map((category) => {
              const catalogCategory = CATALOG_CATEGORIES.find(
                (item) => item.name === category,
              );
              const slug = catalogCategory?.slug ?? "";
              const active = category === "All"
                ? isShopPage && !queryCategorySlug && !dealsOnly
                : selectedCatalogCategory?.slug === slug;
              return (
                <Link
                  className={`category-tab ${active ? "active" : ""}`}
                  to={slug ? `/shop?category=${encodeURIComponent(slug)}` : "/shop"}
                  aria-current={active ? "page" : undefined}
                  key={category}
                  onClick={(event) => {
                    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                      return;
                    }
                    event.preventDefault();
                    browseCatalogCategory(slug);
                  }}
                >
                  {category}
                </Link>
              );
            })}
            <span className="product-count">
              {productsLoading
                ? "Finding lovely things..."
                : productsError
                  ? "Products unavailable"
                  : `Showing ${visibleProducts.length} ${
                      visibleProducts.length === 1 ? "product" : "products"
                    }`}
            </span>
          </nav>

          {isShopPage &&
          queryCategorySlug === "agriculture-livestock" &&
          agriFarmHub ? (
            <AgriFarmHub embedded />
          ) : isShopPage ? (
            <ShopPage
              categoryName={displayCategory === "All" ? "All Categories" : displayCategory}
              productCount={visibleProducts.length}
              products={visibleProducts}
              {...productSectionProps}
            />
          ) : (
            <ProductSection products={visibleProducts} {...productSectionProps} />
          )}
        </section>

        <section className="bottom-note" aria-label="Our promise">
          <span>MADE FOR YOUR MOMENTS</span>
          <span className="bottom-note-flower">✳</span>
          <span>KEEP THE GOOD FEELING GOING</span>
          <span className="bottom-note-flower">✳</span>
          <span>A LITTLE MORE YOU, EVERY DAY</span>
        </section>
      </main>
      <Footer onSelectCategory={browseCategory} />

      {authModalOpen && (
        <AuthModal
          onClose={closeAuthModal}
          onAuthenticated={acceptAuthenticatedUser}
          initialTab={authInitialTab}
          initialRole={authInitialRole}
        />
      )}

      {cartOpen && createPortal(
        <div className="cart-layer">
          <button
            className="cart-backdrop"
            type="button"
            aria-label="Close shopping cart"
            onClick={() => setCartOpen(false)}
          />
          <aside
            className="cart-drawer"
            id="cart-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cart-heading"
          >
            <div className="cart-header">
              <div>
                <span className="cart-eyebrow">YOUR LITTLE TREATS</span>
                <h2 id="cart-heading">Your bag <span>({cartCount})</span></h2>
              </div>
              <button
                className="cart-close"
                type="button"
                aria-label="Close shopping cart"
                onClick={() => setCartOpen(false)}
              >
                <X size={20} />
              </button>
            </div>

            {cartItems.length === 0 ? (
              <div className="cart-empty">
                <span className="cart-empty-icon"><ShoppingBag size={22} /></span>
                <h3>Your bag is taking a little breather.</h3>
                <p>When something feels like you, add it here.</p>
                <button
                  type="button"
                  className="cart-continue"
                  onClick={() => setCartOpen(false)}
                >
                  Find your feel-good <ArrowRight size={15} />
                </button>
              </div>
            ) : (
              <>
                <div className="cart-items" aria-label="Items in your shopping bag">
                  {cartItems.map((item) => (
                    <article className="cart-item" key={item.cartKey}>
                      <img src={item.image} alt="" />
                      <div className="cart-item-info">
                        <span className="cart-item-category">{item.category}</span>
                        <h3>{item.name}</h3>
                        <p>{item.variant ? `Size ${item.variant} · ${item.detail}` : item.detail}</p>
                        <div className="cart-item-bottom">
                          <div className="quantity-control" aria-label={`${item.name} quantity`}>
                            <button
                              type="button"
                              aria-label={`Decrease ${item.name} quantity`}
                              onClick={() => changeCartQuantity(item.cartKey, -1)}
                            >
                              <Minus size={13} />
                            </button>
                            <span aria-live="polite">{item.quantity}</span>
                            <button
                              type="button"
                              aria-label={`Increase ${item.name} quantity`}
                              disabled={
                                cartItems
                                  .filter((cartItem) => cartItem.id === item.id)
                                  .reduce((total, cartItem) => total + cartItem.quantity, 0) >=
                                item.stock
                              }
                              onClick={() => changeCartQuantity(item.cartKey, 1)}
                            >
                              <Plus size={13} />
                            </button>
                          </div>
                          <span className="cart-item-price">
                            {formatKsh(item.price * item.quantity)}
                          </span>
                        </div>
                      </div>
                      <button
                        className="cart-remove"
                        type="button"
                        aria-label={`Remove ${item.name} from cart`}
                        onClick={() => changeCartQuantity(item.cartKey, -item.quantity)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </article>
                  ))}
                </div>

                <div className="cart-summary">
                  <div className="shipping-note">
                    <Sparkles size={14} />
                    {cartTotal >= FREE_SHIPPING_THRESHOLD
                      ? "Lovely! You’ve unlocked complimentary shipping."
                      : `You’re ${formatKsh(FREE_SHIPPING_THRESHOLD - cartTotal)} away from complimentary shipping.`}
                  </div>
                  <div className="cart-subtotal">
                    <span>Subtotal</span>
                    <strong>{formatKsh(cartTotal)}</strong>
                  </div>
                  <p className="cart-shipping-copy">Shipping and taxes calculated at checkout.</p>
                  <button
                    className="checkout-button"
                    type="button"
                    onClick={() => {
                      setCheckoutMessage("");
                      setCartOpen(false);
                      setCheckoutOpen(true);
                    }}
                  >
                    Proceed to Checkout <ArrowRight size={16} />
                  </button>
                  {checkoutMessage && (
                    <p className="checkout-message" role="status">{checkoutMessage}</p>
                  )}
                  <button
                    className="continue-shopping"
                    type="button"
                    onClick={() => setCartOpen(false)}
                  >
                    Continue shopping
                  </button>
                </div>
              </>
            )}
          </aside>
        </div>,
        document.body,
      )}
      {selectedProduct && (
        selectedProduct.category_slug ? (
          <ProductModal
            key={selectedProduct.id}
            product={selectedProduct}
            availableStock={getAvailableStock(selectedProduct)}
            onClose={() => setSelectedProduct(null)}
            onAddToCart={addToCart}
            onBuyNow={buyNow}
          />
        ) : (
          <ProductDetailModal
            key={selectedProduct.id}
            product={selectedProduct}
            availableStock={getAvailableStock(selectedProduct)}
            onClose={() => setSelectedProduct(null)}
            onAddToCart={addToCart}
            onBuyNow={buyNow}
          />
        )
      )}
      {checkoutOpen && (
        <CheckoutModal
          items={cartItems}
          subtotal={cartTotal}
          onClose={() => {
            setCheckoutOpen(false);
            setCartOpen(true);
          }}
          onFinish={() => {
            setCartItems([]);
            setCheckoutMessage("");
            setCheckoutOpen(false);
            setCartOpen(false);
          }}
          onPlaceOrder={async (order) => {
            return createDemoCheckout(order);
          }}
        />
      )}
    </div>
  );
}

export default App;
