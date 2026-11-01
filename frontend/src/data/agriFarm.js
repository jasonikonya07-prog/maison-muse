import { formatKsh } from "./currency.js";

export const AGRI_FARM_CATEGORIES = [
  { label: "All farm listings", value: "agriculture-livestock" },
  { label: "Veterinary Medicines & Treatments", value: "Veterinary Medicines" },
  { label: "Dairy & Beef Cattle", value: "Dairy Cattle" },
  { label: "Goats & Sheep", value: "Goats & Sheep" },
  { label: "Edible Poultry & Fowl", value: "Poultry & Fowl" },
];

export function getFarmerWhatsAppUrl(product) {
  const phone = (
    product.farmer_whatsapp ??
    product.farmerWhatsApp ??
    product.seller?.whatsappPhone ??
    product.seller_whatsapp_phone ??
    ""
  ).replace(/\D/g, "").replace(/^0/, "254");
  if (!phone) return "";

  const farmerName =
    product.farmer_name ?? product.farmerName ?? product.seller?.storeName ?? "Farmer";
  const message = `Hello ${farmerName}, I am interested in buying your ${product.name} (${formatKsh(product.price)}) listed on Maison Muse.`;
  return `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
}
