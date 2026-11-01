import { useState } from "react";

const FALLBACK_IMAGE = "/product-image-unavailable.svg";

export default function ProductImage({ src, ...props }) {
  const [failedSource, setFailedSource] = useState("");
  const imageSource = failedSource === src ? FALLBACK_IMAGE : src;

  return (
    <img
      {...props}
      src={imageSource || FALLBACK_IMAGE}
      onError={() => setFailedSource(src || FALLBACK_IMAGE)}
    />
  );
}
