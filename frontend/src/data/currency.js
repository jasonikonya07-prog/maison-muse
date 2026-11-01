const kshFormatter = new Intl.NumberFormat("en-KE", {
  maximumFractionDigits: 2,
});

export function formatKsh(amount) {
  return `KSh ${kshFormatter.format(amount)}`;
}
