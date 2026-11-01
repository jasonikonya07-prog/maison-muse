import products from "./products.json";

export const PRODUCTS = products;

export const PRODUCT_CATEGORIES = [
  ...new Set(PRODUCTS.map((product) => product.category)),
];
