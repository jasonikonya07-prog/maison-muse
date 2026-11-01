export const categoryRoutes = {
  "/shop": "All",
  "/shop/perfumes": "Perfumes & Fragrances",
  "/shop/press-on-nails": "Press-On Nails",
  "/shop/skincare": "Skincare & Glow",
  "/shop/lip-makeup": "Lip & Makeup Essentials",
  "/shop/hair-accessories": "Hair & Accessories",
  "/shop/accessories": "Hair & Accessories",
};

const pathsByCategory = Object.fromEntries(
  Object.entries(categoryRoutes).map(([path, category]) => [category, path]),
);
pathsByCategory["Hair & Accessories"] = "/shop/hair-accessories";

export const categoryPaths = {
  ...pathsByCategory,
  Perfumes: pathsByCategory["Perfumes & Fragrances"],
  Skincare: pathsByCategory["Skincare & Glow"],
  Accessories: pathsByCategory["Hair & Accessories"],
};
