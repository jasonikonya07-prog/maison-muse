import { useState } from "react";
import { Link } from "react-router-dom";
import { categoryPaths } from "./routes.js";
import { formatKsh } from "./data/currency.js";
import {
  ArrowRight,
  BadgeCheck,
  Check,
  Headphones,
  HeartHandshake,
  Mail,
  RotateCcw,
  Truck,
} from "lucide-react";
import { subscribeToNewsletter } from "./services/api.js";

const trustFeatures = [
  {
    icon: Truck,
    title: "Free delivery",
    description: `On orders of ${formatKsh(5000)} and over`,
  },
  {
    icon: BadgeCheck,
    title: "100% authentic",
    description: "Thoughtfully chosen beauty",
  },
  {
    icon: RotateCcw,
    title: "Easy returns",
    description: "A little help if it isn't quite right",
  },
  {
    icon: Headphones,
    title: "Customer support",
    description: "Real care for your questions",
  },
];

const shopLinks = [
  { label: "Shop everything", category: "All" },
  { label: "Perfumes & fragrances", category: "Perfumes & Fragrances" },
  { label: "Press-on nails", category: "Press-On Nails" },
  { label: "Skincare & glow", category: "Skincare & Glow" },
  { label: "Lip & makeup", category: "Lip & Makeup Essentials" },
  { label: "Hair & accessories", category: "Hair & Accessories" },
];

function Footer({ onSelectCategory }) {
  const [email, setEmail] = useState("");
  const [newsletterStatus, setNewsletterStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submitNewsletter = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setNewsletterStatus({ type: "idle", message: "" });

    try {
      const response = await subscribeToNewsletter(email);
      setNewsletterStatus({ type: "success", message: response.message });
      setEmail("");
    } catch (error) {
      setNewsletterStatus({ type: "error", message: error.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <footer className="store-footer">
      <section
        className="footer-trust-strip"
        id="trust-and-care"
        aria-label="Shopping with Maison Muse"
      >
        {trustFeatures.map(({ icon: Icon, title, description }) => (
          <div className="footer-trust-item" key={title}>
            <span className="footer-trust-icon" aria-hidden="true">
              <Icon size={20} strokeWidth={1.6} />
            </span>
            <span className="footer-trust-copy">
              <strong>{title}</strong>
              <span>{description}</span>
            </span>
          </div>
        ))}
      </section>

      <section className="footer-newsletter" id="newsletter" aria-labelledby="newsletter-heading">
        <div className="footer-newsletter-copy">
          <span className="footer-eyebrow">A NOTE FROM US</span>
          <h2 id="newsletter-heading">
            A little more <em>lovely.</em>
          </h2>
          <p>Get new finds, feel-good rituals, and Maison Muse news in your inbox.</p>
        </div>
        <form className="footer-newsletter-form" onSubmit={submitNewsletter}>
          <label className="visually-hidden" htmlFor="footer-newsletter-email">
            Your email address
          </label>
          <div className="footer-email-field">
            <Mail size={17} aria-hidden="true" />
            <input
              id="footer-newsletter-email"
              type="email"
              name="email"
              autoComplete="email"
              placeholder="Your email address"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (newsletterStatus.type !== "idle") {
                  setNewsletterStatus({ type: "idle", message: "" });
                }
              }}
              maxLength={254}
              required
              disabled={isSubmitting}
            />
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Joining…" : "Join us"}
              {!isSubmitting && <ArrowRight size={15} aria-hidden="true" />}
            </button>
          </div>
          <p className="footer-newsletter-privacy">
            By signing up, you agree to receive occasional email updates. Unsubscribe anytime.
          </p>
          <p
            className={`footer-newsletter-status is-${newsletterStatus.type}`}
            role={newsletterStatus.type === "error" ? "alert" : "status"}
            aria-live="polite"
          >
            {newsletterStatus.type === "success" && <Check size={14} aria-hidden="true" />}
            {newsletterStatus.message}
          </p>
        </form>
      </section>

      <div className="footer-directory">
        <div className="footer-brand-column">
          <Link className="wordmark footer-wordmark" to="/" aria-label="Maison Muse home">
            maison <span>muse</span>
            <i aria-hidden="true">.</i>
          </Link>
          <p>Small beauty rituals, lovely little luxuries, and a little more you, every day.</p>
          <span className="footer-brand-note">
            <HeartHandshake size={15} aria-hidden="true" />
            Made for your moments
          </span>
        </div>

        <nav className="footer-link-group" aria-label="Shop categories">
          <h2>Shop</h2>
          {shopLinks.map(({ label, category }) => (
            <Link
              to={categoryPaths[category]}
              key={category}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                  return;
                }
                event.preventDefault();
                onSelectCategory(category);
              }}
            >
              {label}
            </Link>
          ))}
        </nav>

        <nav className="footer-link-group" aria-label="Maison Muse information">
          <h2>Maison Muse</h2>
          <a href="#footer-description">Our story</a>
          <a href="#trust-and-care">Delivery & returns</a>
          <a href="#newsletter">Customer care</a>
          <a href="#newsletter">Email updates</a>
          <Link to="/seller">Sell with Maison Muse</Link>
        </nav>

        <div className="footer-payment-column">
          <h2>Checkout options</h2>
          <p>Secure online payments powered by Pesapal.</p>
          <div className="footer-payment-badges" aria-label="Secure Pesapal checkout">
            <span>Pesapal</span>
          </div>
          <span className="footer-secure-note">Payment details are entered on Pesapal.</span>
        </div>
      </div>

      <section className="footer-seo-copy" id="footer-description" aria-labelledby="footer-seo-heading">
        <h2 id="footer-seo-heading">Beauty, made personal at Maison Muse</h2>
        <p>
          Discover your next signature scent with our edit of perfumes and
          fragrance, find an at-home manicure you love with press-on nails, and
          build feel-good routines with everyday skincare. Maison Muse brings
          together beauty essentials and thoughtful accessories for the little
          rituals that make getting ready feel like you. Explore perfumes,
          reusable nail sets, skincare favorites, and finishing touches in one
          considered online beauty shop.
        </p>
      </section>

      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} Maison Muse</span>
        <span>For all the ways you show up as you.</span>
      </div>
    </footer>
  );
}

export default Footer;
