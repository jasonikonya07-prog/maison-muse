import { Link, useLocation } from "react-router-dom";
import { CATALOG_CATEGORIES } from "../data/catalogCategories.js";
import "./CategoryBar.css";

function CategoryBar({ activeSlug = "", onSelectCategory }) {
  const location = useLocation();
  const selectCategory = (event, slug) => {
    if (
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    onSelectCategory(slug);
  };

  return (
    <nav className="catalog-category-bar" aria-label="Browse all categories">
      <div className="catalog-category-scroll">
        <Link
          className={`catalog-category-link ${activeSlug ? "" : "active"}`}
          to="/shop"
          aria-current={!activeSlug ? "page" : undefined}
          onClick={(event) => selectCategory(event, "")}
        >
          All categories
        </Link>
        {CATALOG_CATEGORIES.map(({ name, slug }) => (
          <Link
            className={`catalog-category-link ${activeSlug === slug ? "active" : ""}`}
            to={`/shop?category=${encodeURIComponent(slug)}`}
            aria-current={activeSlug === slug ? "page" : undefined}
            key={slug}
            onClick={(event) => selectCategory(event, slug)}
          >
            {name}
          </Link>
        ))}
        <Link
          className={`catalog-category-link ${location.pathname === "/shop" && location.search.includes("agriculture-livestock") ? "active" : ""}`}
          to="/shop?category=agriculture-livestock"
          aria-current={location.pathname === "/shop" && location.search.includes("agriculture-livestock") ? "page" : undefined}
          onClick={(event) => selectCategory(event, "agriculture-livestock")}
        >
          Farm Direct
        </Link>
      </div>
    </nav>
  );
}

export default CategoryBar;
