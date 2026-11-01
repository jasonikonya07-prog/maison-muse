import ProductSection from "../components/ProductSection.jsx";

function ShopPage({
  categoryName,
  productCount,
  products,
  ...productSectionProps
}) {
  return (
    <div className="shop-page-catalog">
      <p className="shop-page-result-summary" aria-live="polite">
        {productSectionProps.loading
          ? "Loading verified products…"
          : `Showing ${productCount} verified ${productCount === 1 ? "product" : "products"} in ${categoryName}`}
      </p>
      <ProductSection products={products} {...productSectionProps} />
    </div>
  );
}

export default ShopPage;
