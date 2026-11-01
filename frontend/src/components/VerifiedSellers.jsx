import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, MapPin, Search, ShieldCheck, Star, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { fetchVerifiedSellers } from "../services/api.js";
import { useFeatures } from "../context/FeatureContext.jsx";
import "./VerifiedSellers.css";

const categoryFilters = [
  "All Sellers",
  "Perfumeries",
  "Nail Studios",
  "Skincare Labs",
];
const PAGE_SIZE = 24;

function VerifiedSellers({ directory = false }) {
  const { verifiedSellerBadge } = useFeatures();
  const [sellers, setSellers] = useState([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All Sellers");
  const [sort, setSort] = useState("popularity");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const sentinelRef = useRef(null);

  const resetResults = useCallback((update) => {
    setOffset(0);
    setSellers([]);
    setError("");
    update();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchVerifiedSellers({
      search,
      category,
      sort,
      limit: directory ? PAGE_SIZE : 6,
      offset,
      signal: controller.signal,
    })
      .then((result) => {
        setSellers((current) =>
          offset === 0 ? result.items : [...current, ...result.items],
        );
        setTotal(result.total);
      })
      .catch((loadError) => {
        if (loadError.name !== "AbortError") setError(loadError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [category, directory, offset, retry, search, sort]);

  useEffect(() => {
    if (!directory || !sentinelRef.current || loading || sellers.length >= total) {
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setOffset((current) => current + PAGE_SIZE);
      },
      { rootMargin: "240px" },
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [directory, loading, sellers.length, total]);

  return (
    <section
      className={`verified-sellers-section ${directory ? "is-directory" : ""}`}
      id="verified-boutiques"
      aria-labelledby="verified-sellers-heading"
    >
      <header className="verified-sellers-heading">
        <div>
          <span className="verified-sellers-eyebrow">THE MAISON MUSE COLLECTIVE</span>
          <h2 id="verified-sellers-heading">
            Curated Beauty Boutiques
          </h2>
          <p>Meet the independent beauty businesses behind your next favorite find.</p>
        </div>
        {!directory && (
          <Link className="verified-sellers-view-all" to="/boutiques">
            Explore all boutiques <ArrowRight size={15} />
          </Link>
        )}
      </header>

      <label className="verified-sellers-search">
        <Search size={17} aria-hidden="true" />
        <input
          type="search"
          value={search}
          onChange={(event) => resetResults(() => setSearch(event.target.value))}
          placeholder="Search by store name"
          aria-label="Search verified boutiques by store name"
        />
      </label>

      <div className="verified-sellers-toolbar">
        <div className="verified-seller-filters" role="group" aria-label="Filter boutiques by category">
          {categoryFilters.map((filter) => (
            <button
              type="button"
              key={filter}
              className={category === filter ? "is-active" : ""}
              aria-pressed={category === filter}
              onClick={() => resetResults(() => setCategory(filter))}
            >
              {filter}
            </button>
          ))}
        </div>
        <label className="verified-seller-sort">
          <span>Sort by</span>
          <select
            value={sort}
            onChange={(event) => resetResults(() => setSort(event.target.value))}
          >
            <option value="popularity">Most popular</option>
            <option value="rating">Top rated</option>
          </select>
        </label>
      </div>

      <p className="verified-sellers-count" aria-live="polite">
        {loading && !sellers.length
          ? "Discovering verified boutiques…"
          : `${total.toLocaleString()} verified ${total === 1 ? "boutique" : "boutiques"}`}
      </p>

      {error ? (
        <div className="verified-sellers-state" role="alert">
          <Store size={22} />
          <p>{error}</p>
          <button
            type="button"
            onClick={() => {
              setError("");
              setRetry((current) => current + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : sellers.length ? (
        <>
          <div className="verified-seller-grid">
            {sellers.map((seller) => (
              <article className="verified-seller-card" key={seller.id}>
                <Link
                  className="verified-seller-cover"
                  to={`/boutiques/${encodeURIComponent(seller.store_slug)}`}
                  aria-label={`Explore ${seller.store_name}`}
                >
                  {seller.banner_url ? (
                    <img src={seller.banner_url} alt="" loading="lazy" />
                  ) : seller.product_samples[0]?.image ? (
                    <img src={seller.product_samples[0].image} alt="" loading="lazy" />
                  ) : (
                    <span className="verified-seller-cover-placeholder"><Store size={28} /></span>
                  )}
                  {verifiedSellerBadge && (
                    <span className="verified-seller-badge">
                      <ShieldCheck size={16} fill="currentColor" />
                      <span>VERIFIED</span>
                    </span>
                  )}
                </Link>
                <div className="verified-seller-card-body">
                  <div className="verified-seller-identity">
                    {seller.logo_url ? (
                      <img src={seller.logo_url} alt="" loading="lazy" />
                    ) : (
                      <span className="verified-seller-logo-placeholder">
                        {seller.store_name.slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <div>
                      <h3>{seller.store_name}</h3>
                      {seller.city && (
                        <span className="verified-seller-city">
                          <MapPin size={11} /> {seller.city}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="verified-seller-category">{seller.category}</p>
                  <p className="verified-seller-rating">
                    <Star size={13} fill="currentColor" />
                    {Number(seller.rating).toFixed(1)}
                    <span>({seller.sales_count.toLocaleString()} sales)</span>
                  </p>
                  <p className="verified-seller-listing-count">
                    {seller.total_listings.toLocaleString()}{" "}
                    {seller.total_listings === 1 ? "listed item" : "listed items"}
                  </p>
                  {seller.product_samples.length > 0 && (
                    <div className="verified-seller-samples" aria-label="Boutique product samples">
                      {seller.product_samples.map((product) => (
                        <img
                          key={product.name}
                          src={product.image}
                          alt={product.name}
                          loading="lazy"
                        />
                      ))}
                    </div>
                  )}
                  <Link
                    className="verified-seller-explore"
                    to={`/boutiques/${encodeURIComponent(seller.store_slug)}`}
                  >
                    Explore Store <ArrowRight size={14} />
                  </Link>
                </div>
              </article>
            ))}
          </div>
          {directory && (
            <div className="verified-sellers-pagination" ref={sentinelRef}>
              {loading && <span>Finding more boutiques…</span>}
              {!loading && sellers.length >= total && (
                <span>You’ve explored all {total.toLocaleString()} verified boutiques.</span>
              )}
            </div>
          )}
        </>
      ) : (
        !loading && (
          <div className="verified-sellers-state">
            <Store size={22} />
            <p>No verified boutiques match those filters yet.</p>
          </div>
        )
      )}
    </section>
  );
}

export default VerifiedSellers;
