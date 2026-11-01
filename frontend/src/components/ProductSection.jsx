import { useMemo, useState } from "react";
import {
  Heart,
  MessageCircle,
  Phone,
  Search,
  ShieldCheck,
  ShoppingBag,
  Star,
} from "lucide-react";
import { Link } from "react-router-dom";
import { formatKsh } from "../data/currency.js";
import ProductImage from "./ProductImage.jsx";
import { getFarmerWhatsAppUrl } from "../data/agriFarm.js";
import { useFeatures } from "../context/FeatureContext.jsx";
import "../seller/Marketplace.css";

const sortOptions = [
  { value: "featured", label: "Featured" },
  { value: "price-asc", label: "Price: Low to High" },
  { value: "price-desc", label: "Price: High to Low" },
  { value: "rating", label: "Highest Rated" },
  { value: "best-sellers", label: "Best Sellers" },
];
const tagColorValues = {
  "bg-rose-600": "#e11d48",
  "bg-purple-600": "#9333ea",
  "bg-amber-500": "#f59e0b",
  "bg-[#e61601]": "#e61601",
  "bg-emerald-600": "#059669",
};

function ProductSection({
  products,
  loading,
  error,
  onRetry,
  wishlist,
  onToggleWishlist,
  onAddToCart,
  onSelectProduct,
  getAvailableStock,
  search,
  onSearchChange,
  showWishlist,
  onBrowseAll,
}) {
  const [sortBy, setSortBy] = useState("featured");
  const { verifiedSellerBadge, whatsappDirectBypass } = useFeatures();
  const visibleProducts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const matchingProducts = products.filter((product) => {
      if (!query) return true;
      return `${product.name} ${product.brand}`.toLocaleLowerCase().includes(query);
    });

    switch (sortBy) {
      case "price-asc":
        return [...matchingProducts].sort((a, b) => a.price - b.price);
      case "price-desc":
        return [...matchingProducts].sort((a, b) => b.price - a.price);
      case "rating":
        return [...matchingProducts].sort((a, b) => b.rating - a.rating);
      case "best-sellers":
        return [...matchingProducts].sort(
          (a, b) => b.reviewsCount - a.reviewsCount || b.rating - a.rating,
        );
      default:
        return matchingProducts;
    }
  }, [products, search, sortBy]);

  return (
    <>
      <div className="product-toolbar">
        <label className="product-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            aria-label="Search products by name or brand"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search products or brands"
          />
        </label>
        <label className="product-sort">
          <span>Sort by</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            {sortOptions.map((option) => (
              <option value={option.value} key={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <span className="product-results-count" aria-live="polite">
          Showing {visibleProducts.length} {visibleProducts.length === 1 ? "product" : "products"}
        </span>
      </div>

      <div className="product-grid" id="products" aria-busy={loading}>
        {loading ? (
          Array.from({ length: 4 }, (_, index) => (
            <div className="product-skeleton" key={`product-skeleton-${index}`} aria-hidden="true">
              <div className="product-skeleton-image" />
              <div className="product-skeleton-line" />
              <div className="product-skeleton-line short" />
            </div>
          ))
        ) : error ? (
          <div className="products-error" role="alert">
            <Search size={22} />
            <h3>We couldn’t load the lovely things.</h3>
            <p>{error}</p>
            <button type="button" onClick={onRetry}>Try again</button>
          </div>
        ) : visibleProducts.length ? (
          visibleProducts.map((product) => {
            const isWishlisted = wishlist.includes(product.id);
            const availableStock = getAvailableStock(product);
            const farmerWhatsAppUrl = product.is_agri_product && whatsappDirectBypass
              ? getFarmerWhatsAppUrl(product)
              : "";
            return (
              <article
                className="product-card"
                key={product.id}
                tabIndex={0}
                aria-label={`View details for ${product.name}`}
                onClick={() => onSelectProduct(product)}
                onKeyDown={(event) => {
                  if (
                    event.currentTarget === event.target &&
                    (event.key === "Enter" || event.key === " ")
                  ) {
                    event.preventDefault();
                    onSelectProduct(product);
                  }
                }}
              >
                <div className={`product-image-wrap tone-${product.tone}`}>
                  <ProductImage src={product.image} alt={product.name} loading="lazy" />
                  <span
                    className={`product-tag ${product.tagColor ?? ""}`}
                    style={{
                      backgroundColor: tagColorValues[product.tagColor],
                      color: product.tagColor ? "white" : undefined,
                    }}
                  >
                    {product.tag}
                  </span>
                  {product.discount && (
                    <span className="product-discount">{product.discount}</span>
                  )}
                  <span className="product-category">{product.category}</span>
                  <button
                    className={`favorite-button ${isWishlisted ? "is-favorite" : ""}`}
                    type="button"
                    aria-label={
                      isWishlisted
                        ? `Remove ${product.name} from wishlist`
                        : `Add ${product.name} to wishlist`
                    }
                    aria-pressed={isWishlisted}
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleWishlist(product.id);
                    }}
                  >
                    <Heart size={17} fill={isWishlisted ? "currentColor" : "none"} />
                  </button>
                  {product.is_agri_product ? (
                    farmerWhatsAppUrl ? (
                      <a
                        className="quick-add is-agri-contact"
                        href={farmerWhatsAppUrl}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Contact farmer about ${product.name} on WhatsApp`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        <span>Contact Farmer on WhatsApp</span>
                        <MessageCircle size={15} />
                      </a>
                    ) : (
                      <span className="quick-add is-agri-contact is-unavailable">
                        {whatsappDirectBypass ? "Farmer contact unavailable" : "Direct contact unavailable"}
                      </span>
                    )
                  ) : (
                    <button
                      className="quick-add"
                      type="button"
                      disabled={availableStock === 0 || product.seller?.holidayMode}
                      onClick={(event) => {
                        event.stopPropagation();
                        onAddToCart(
                          product,
                          1,
                          product.nailSizes?.[2] ??
                            (product.variants?.[0]
                              ? `${product.variants[0].name}: ${product.variants[0].options[0]}`
                              : ""),
                        );
                      }}
                    >
                      <span>{product.seller?.holidayMode ? "Seller on pause" : availableStock > 0 ? "Add to Bag" : "Sold out"}</span>
                      <span>{formatKsh(product.price)}</span>
                      <ShoppingBag size={14} />
                    </button>
                  )}
                </div>
                <div className="product-info">
                  <div>
                    <span className="product-brand">{product.brand}</span>
                    <h3>{product.name}</h3>
                    <p>{product.detail}</p>
                    {product.seller?.storeName && (
                      <>
                        <Link
                          className="product-seller-attribution"
                          to={`/boutiques/${encodeURIComponent(product.seller.storeSlug)}`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          Sold &amp; fulfilled by {product.seller.storeName}
                          {verifiedSellerBadge && product.seller.verified !== false && (
                            <ShieldCheck
                              className="product-seller-verified"
                              size={13}
                              aria-label="Verified seller"
                            />
                          )}
                        </Link>
                        {(product.seller.businessPhone || product.seller.whatsappPhone) && (
                          <span className="product-seller-contact">
                            <Phone size={11} aria-hidden="true" />
                            Support / WhatsApp:
                            <a
                              href={`tel:${(product.seller.businessPhone || product.seller.whatsappPhone).replace(/[^\d+]/g, "")}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {product.seller.businessPhone || product.seller.whatsappPhone}
                            </a>
                            <a
                              href={`https://wa.me/${(product.seller.whatsappPhone || product.seller.businessPhone).replace(/\D/g, "").replace(/^0/, "254")}`}
                              target="_blank"
                              rel="noreferrer"
                              aria-label={`Chat with ${product.seller.storeName} on WhatsApp`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              <MessageCircle size={13} />
                            </a>
                          </span>
                        )}
                        {product.seller.holidayMode && (
                          <small className="product-seller-holiday">Boutique is on holiday pause</small>
                        )}
                      </>
                    )}
                    {product.rating !== null && (
                      <div
                        className="product-rating"
                        aria-label={`${product.rating} out of 5 stars, ${product.reviewsCount} reviews`}
                      >
                        <Star size={11} fill="currentColor" />
                        <span>{product.rating.toFixed(1)}</span>
                        <span className="rating-review-count">
                          · {product.reviewsCount} reviews
                        </span>
                      </div>
                    )}
                  </div>
                  <span className="product-price">
                    <strong>{formatKsh(product.price)}</strong>
                    {product.oldPrice && (
                      <del>{formatKsh(product.oldPrice)}</del>
                    )}
                  </span>
                </div>
              </article>
            );
          })
        ) : (
          <div className="empty-state">
            <Search size={22} />
            <h3>No lovely finds just yet</h3>
            <p>
              {showWishlist
                ? "Tap the heart on anything you love to save it here."
                : "Try another search or choose a different category."}
            </p>
            <button
              type="button"
              onClick={showWishlist ? onBrowseAll : () => onSearchChange("")}
            >
              {showWishlist ? "Browse all finds" : "Clear filters"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export default ProductSection;
