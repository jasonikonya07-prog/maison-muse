import { useEffect, useState } from "react";
import { Download, MessageCircle, Printer, RefreshCw, Send } from "lucide-react";
import { formatKsh } from "../../data/currency.js";
import {
  confirmSellerManifestDropoff,
  createSellerBranch,
  createSellerManifest,
  createSellerVasRequest,
  fetchSellerBranches,
  fetchSellerFulfillment,
  fetchSellerInsights,
  fetchSellerManifests,
  fetchSellerMessages,
  fetchSellerNotificationPreferences,
  fetchSellerQcQueue,
  fetchSellerRepricingRules,
  fetchSellerRestockPlan,
  fetchSellerTeam,
  fetchSellerWeeklyStatement,
  inviteSellerTeamMember,
  replyToSellerMessage,
  requestSellerOrderReview,
  requestSellerRestock,
  revokeSellerTeamMember,
  submitSellerProductQc,
  updateSellerBranchInventory,
  updateSellerFulfillmentMode,
  updateSellerNotificationPreferences,
  updateSellerRepricingRule,
} from "../../services/api.js";

const rolePermissions = {
  "Inventory Clerk": ["Read catalog", "Update stock"],
  "Fulfillment Manager": ["Read orders", "Update fulfillment", "Read messages", "Reply to messages"],
  Accountant: ["Read financial ledger", "Read statements", "Read payouts"],
};

function SellerNotificationSettings({ demoMode }) {
  const [preferences, setPreferences] = useState({
    low_stock_sms: false,
    low_stock_whatsapp: false,
    incoming_orders_sms: false,
    incoming_orders_whatsapp: false,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (demoMode) return undefined;
    let active = true;
    fetchSellerNotificationPreferences()
      .then((result) => {
        if (active) {
          setPreferences({
            low_stock_sms: result.low_stock_sms,
            low_stock_whatsapp: result.low_stock_whatsapp,
            incoming_orders_sms: result.incoming_orders_sms,
            incoming_orders_whatsapp: result.incoming_orders_whatsapp,
          });
        }
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      });
    return () => { active = false; };
  }, [demoMode]);

  async function savePreferences(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await updateSellerNotificationPreferences(preferences);
      setError("Preferences saved. SMS and WhatsApp delivery is not configured.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">ALERT PREFERENCES</span><h2>Order &amp; stock notifications</h2></div></header>
      <p className="seller-operation-note">Low-stock alerts use a threshold below 5 units. Preferences are saved, but no SMS or WhatsApp provider is connected.</p>
      {error && <p className={error.includes("saved") ? "seller-operation-note" : "marketplace-error"} role="status">{error}</p>}
      <form className="seller-advanced-form" onSubmit={savePreferences}>
        <fieldset>
          <legend>Low stock (&lt; 5 units)</legend>
          {[
            ["low_stock_sms", "SMS"],
            ["low_stock_whatsapp", "WhatsApp"],
          ].map(([key, label]) => (
            <label key={key}><input type="checkbox" disabled={demoMode} checked={preferences[key]} onChange={(event) => setPreferences((current) => ({ ...current, [key]: event.target.checked }))} /> {label}</label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Incoming orders</legend>
          {[
            ["incoming_orders_sms", "SMS"],
            ["incoming_orders_whatsapp", "WhatsApp"],
          ].map(([key, label]) => (
            <label key={key}><input type="checkbox" disabled={demoMode} checked={preferences[key]} onChange={(event) => setPreferences((current) => ({ ...current, [key]: event.target.checked }))} /> {label}</label>
          ))}
        </fieldset>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || saving}>{saving ? "Saving…" : "Save preferences"}</button>
      </form>
    </section>
  );
}

function TeamManager({ data, demoMode, refresh, setError, setNotice }) {
  const [invitation, setInvitation] = useState({ email: "", full_name: "", role: "Inventory Clerk" });
  const [busy, setBusy] = useState(false);

  async function invite(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await inviteSellerTeamMember(invitation);
      setNotice("Team invite saved. Email delivery is not configured.");
      setInvitation({ email: "", full_name: "", role: "Inventory Clerk" });
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(member) {
    setBusy(true);
    setError("");
    try {
      await revokeSellerTeamMember(member.id);
      setNotice(`Access revoked for ${member.email}.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">TEAM ACCESS</span><h2>Staff &amp; permissions</h2></div></header>
      <p className="seller-operation-note">Role permissions are stored with the invitation. Team sign-in and invitation email delivery are not configured, so members cannot access the seller account yet.</p>
      <form className="seller-advanced-form" onSubmit={invite}>
        <label>Email<input type="email" required maxLength="254" value={invitation.email} onChange={(event) => setInvitation((current) => ({ ...current, email: event.target.value }))} /></label>
        <label>Name<input maxLength="120" value={invitation.full_name} onChange={(event) => setInvitation((current) => ({ ...current, full_name: event.target.value }))} /></label>
        <label>Role<select value={invitation.role} onChange={(event) => setInvitation((current) => ({ ...current, role: event.target.value }))}>{Object.keys(rolePermissions).map((role) => <option key={role}>{role}</option>)}</select></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || busy}>{busy ? "Saving…" : "Invite team member"}</button>
      </form>
      <div className="seller-advanced-list">
        {data.map((member) => (
          <article key={member.id}>
            <div><strong>{member.full_name || member.email} · {member.role}</strong><small>{member.email} · {member.status}</small><small>{member.permissions.join(" · ")}</small></div>
            {member.status !== "REVOKED" && <button className="marketplace-button secondary" type="button" disabled={demoMode || busy} onClick={() => revoke(member)}>Revoke</button>}
          </article>
        ))}
        {!data.length && <p className="marketplace-empty">No staff invitations yet.</p>}
      </div>
    </section>
  );
}

function ChatInbox({ messages, demoMode, refresh, setError, setNotice }) {
  const groups = messages.reduce((result, message) => {
    result[message.conversation_id] ??= [];
    result[message.conversation_id].unshift(message);
    return result;
  }, {});
  const conversations = Object.entries(groups);
  const [selected, setSelected] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const conversationId = selected || conversations[0]?.[0] || "";
  const activeMessages = groups[conversationId] ?? [];

  async function sendReply(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await replyToSellerMessage({ conversation_id: conversationId, body });
      setBody("");
      setNotice("Reply saved. Buyer delivery requires a messaging provider.");
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">BUYER CONVERSATIONS</span><h2>Customer messages</h2></div><button className="marketplace-button secondary" type="button" onClick={() => refresh().catch(setError)}><RefreshCw size={14} /> Refresh</button></header>
      <p className="seller-operation-note">Messages are stored and polled on this page. Replies are not delivered to buyers until a messaging provider is connected.</p>
      {conversations.length ? (
        <div className="seller-chat-layout">
          <nav aria-label="Conversations">{conversations.map(([id, items]) => <button type="button" key={id} className={conversationId === id ? "active" : ""} onClick={() => setSelected(id)}><MessageCircle size={15} /><span>{items.at(-1)?.sender_name || items.at(-1)?.product_name || "Buyer"}<small>{items.at(-1)?.product_name || "Product inquiry"}</small></span></button>)}</nav>
          <div className="seller-chat-thread">
            <div>{activeMessages.map((message) => <article className={`seller-chat-message ${message.sender_role.toLowerCase()}`} key={message.id}><strong>{message.sender_name}</strong><p>{message.body}</p><small>{new Date(message.created_at).toLocaleString()}</small></article>)}</div>
            <form onSubmit={sendReply}><label className="visually-hidden" htmlFor="seller-chat-reply">Reply to buyer</label><textarea id="seller-chat-reply" required maxLength="2000" rows="3" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Reply about sizing, custom requests, or delivery…" /><button className="marketplace-button primary" disabled={demoMode || busy || !conversationId}><Send size={14} /> Send reply</button></form>
          </div>
        </div>
      ) : <p className="marketplace-empty">Buyer inquiries will appear here.</p>}
    </section>
  );
}

function LogisticsManager({ products, modes, manifests, demoMode, refresh, setError, setNotice }) {
  const [productId, setProductId] = useState("");
  const [hub, setHub] = useState("Nairobi CBD");
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);

  async function changeMode(id, mode) {
    try {
      await updateSellerFulfillmentMode(id, mode);
      setNotice("Fulfillment mode updated.");
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  async function createManifest(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const manifest = await createSellerManifest({ hub_name: hub, items: [{ product_id: productId, quantity: Number(quantity) }] });
      setNotice(`Drop-off slip ${manifest.reference} is ready to print.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function markDropped(manifestId) {
    try {
      await confirmSellerManifestDropoff(manifestId);
      setNotice("Drop-off recorded; warehouse stock updated.");
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  async function printManifest(manifest) {
    let popup;
    try {
      popup = window.open("", "_blank");
      if (!popup) {
        setError("Allow pop-ups to print the drop-off slip.");
        return;
      }
      popup.opener = null;
      const { default: QRCode } = await import("qrcode");
      const qr = await QRCode.toDataURL(manifest.reference, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 180,
      });
      const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]);
      const items = manifest.items.map((item) => `<li>${item.quantity} × ${escapeHtml(item.product_name || item.product_id)}</li>`).join("");
      popup.document.write(`<!doctype html><title>Drop-off ${escapeHtml(manifest.reference)}</title><style>body{font:16px Arial;margin:48px}h1{font-size:24px}li{margin:12px 0}.qr{width:160px}</style><h1>Maison Muse VDO Drop-off</h1><p>Manifest: ${escapeHtml(manifest.reference)}</p><p>Hub: ${escapeHtml(manifest.hub_name)}</p><ul>${items}</ul><p>Scan drop-off reference</p><img class="qr" src="${qr}" alt="QR code for ${escapeHtml(manifest.reference)}"><button onclick="window.print()">Print</button>`);
      popup.document.close();
    } catch (printError) {
      popup?.close();
      setError(`Could not create the manifest slip: ${printError.message}`);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">WAREHOUSE &amp; VDO LOGISTICS</span><h2>Fulfillment modes &amp; drop-offs</h2></div></header>
      <p className="seller-operation-note">Manifest slips use a printable reference code. Stock is reserved while a manifest is ready and moved to the warehouse ledger when marked dropped off; marketplace stock is not automatically reconciled.</p>
      <div className="seller-advanced-list">{products.map((product) => {
        const mode = modes.find((item) => item.id === product.id)?.fulfillment_mode || "SELF_FULFILLMENT";
        return <article key={product.id}><div><strong>{product.name}</strong><small>{product.stock} units · {mode.replaceAll("_", " ")}</small></div><select aria-label={`Fulfillment mode for ${product.name}`} disabled={demoMode} value={mode} onChange={(event) => changeMode(product.id, event.target.value)}><option value="SELF_FULFILLMENT">Self-fulfillment</option><option value="MAISON_EXPRESS">Maison Express / Consignment</option></select></article>;
      })}</div>
      <form className="seller-advanced-form" onSubmit={createManifest}>
        <label>Product<select required value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Select product</option>{products.filter((product) => modes.find((item) => item.id === product.id)?.fulfillment_mode === "MAISON_EXPRESS").map((product) => <option key={product.id} value={product.id}>{product.name} · {product.stock} available</option>)}</select></label>
        <label>Drop-off hub<select value={hub} onChange={(event) => setHub(event.target.value)}><option>Nairobi CBD</option><option>Westlands</option><option>Mombasa</option></select></label>
        <label>Quantity<input type="number" min="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || busy || !productId}>Create manifest</button>
      </form>
      <div className="seller-advanced-list">{manifests.map((manifest) => <article key={manifest.id}><div><strong>{manifest.reference} · {manifest.hub_name}</strong><small>{manifest.status} · {manifest.items.map((item) => `${item.quantity} × ${item.product_name}`).join(", ")}</small></div><div className="seller-return-actions"><button type="button" className="marketplace-button secondary" onClick={() => printManifest(manifest)}><Printer size={14} /> Print</button>{manifest.status === "READY" && <button type="button" className="marketplace-button primary" disabled={demoMode} onClick={() => markDropped(manifest.id)}>Confirm drop-off</button>}</div></article>)}</div>
    </section>
  );
}

function CatalogHealth({ products, queue, demoMode, refresh, setError, setNotice }) {
  const [productId, setProductId] = useState("");
  const [vas, setVas] = useState("BACKGROUND_CLEANUP");
  const product = products.find((item) => item.id === productId);

  async function submitQc(id) {
    try {
      await submitSellerProductQc(id);
      setNotice("Listing submitted for administrator QC review.");
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  async function requestVas(event) {
    event.preventDefault();
    try {
      await createSellerVasRequest({ product_id: productId, service_type: vas });
      setNotice("Studio service request added to the manual queue.");
    } catch (error) {
      setError(error.message);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">CATALOG HEALTH</span><h2>Quality control &amp; studio services</h2></div></header>
      <div className="seller-advanced-list">{queue.map((item) => <article key={item.id}><div><strong>{item.name}</strong><small>{item.sku || "No SKU"} · {item.qc_status.replaceAll("_", " ")} · Product: {item.product_status}</small>{item.audit?.notes && <small>{item.audit.notes}</small>}</div><div className="seller-return-actions">{item.qc_status === "PENDING_QC" ? <span className="seller-status-badge">Awaiting admin review</span> : <button className="marketplace-button primary" type="button" disabled={demoMode} onClick={() => submitQc(item.id)}>{item.qc_status === "REJECTED_IMAGE_QUALITY" ? "Resubmit after fixes" : "Submit for QC"}</button>}</div></article>)}</div>
      <form className="seller-advanced-form" onSubmit={requestVas}>
        <label>Product<select required value={productId} onChange={(event) => setProductId(event.target.value)}><option value="">Choose a listing</option>{products.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label>Studio service<select value={vas} onChange={(event) => setVas(event.target.value)}><option value="BACKGROUND_CLEANUP">Background cleanup</option><option value="SEO_ENHANCEMENT">SEO description enhancement</option></select></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || !product}>Request service</button>
      </form>
      <p className="seller-operation-note">New listings are saved as drafts and stay hidden until an administrator approves QC. Professional photography and copy services are queued for manual fulfillment.</p>
    </section>
  );
}

function VendorStatement({ statement }) {
  function exportCsv() {
    const rows = [
      ["Order", "Date", "Gross", "Commission", "Estimated commission VAT", "Shipping contribution", "Net payout"],
      ...statement.rows.map((row) => [row.order_number, row.created_at, row.gross_revenue, row.commission, row.commission_vat, row.shipping_contribution, row.net_balance]),
    ];
    const content = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "maison-muse-weekly-statement.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">LAST 7 DAYS</span><h2>Itemized financial statement</h2></div><button type="button" className="marketplace-button secondary" onClick={exportCsv}><Download size={14} /> Download CSV</button></header>
      {statement.notes?.map((note) => <p className="seller-operation-note" key={note}>{note}</p>)}
      <div className="seller-advanced-grid">{Object.entries(statement.totals ?? {}).map(([key, amount]) => <article className="seller-advanced-card" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatKsh(amount)}</strong></article>)}</div>
      {statement.rows.length ? <div className="seller-table-scroll"><table><thead><tr><th>Order</th><th>Gross</th><th>Commission</th><th>VAT estimate</th><th>Net payout</th></tr></thead><tbody>{statement.rows.map((row) => <tr key={row.sub_order_id}><td>{row.order_number}</td><td>{formatKsh(row.gross_revenue)}</td><td>{formatKsh(row.commission)}</td><td>{formatKsh(row.commission_vat)}</td><td>{formatKsh(row.net_balance)}</td></tr>)}</tbody></table></div> : <p className="marketplace-empty">No orders were recorded in the last seven days.</p>}
      <h3>Cancellation &amp; stockout audit</h3>
      {statement.penalties.length ? <div className="seller-advanced-list">{statement.penalties.map((item) => <article key={item.id}><div><strong>{item.reason}</strong><small>{item.status} · {new Date(item.created_at).toLocaleDateString()}</small></div><strong>{formatKsh(item.amount)}</strong></article>)}</div> : <p className="marketplace-empty">No penalty events are currently recorded.</p>}
    </section>
  );
}

function DynamicRepricer({ products, rules, demoMode, refresh, setError, setNotice }) {
  const [productId, setProductId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [rule, setRule] = useState("CLEARANCE_DISCOUNT");
  const [busy, setBusy] = useState(false);
  const product = products.find((item) => item.id === productId);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await updateSellerRepricingRule(productId, {
        min_price: Number(minPrice),
        max_price: Number(maxPrice),
        rule,
      });
      setNotice(`Price rule applied at ${formatKsh(result.applied_price)}.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">PRICING AUTOMATION</span><h2>Dynamic repricer</h2></div></header>
      <p className="seller-operation-note">Rules apply immediately within your price guards. Market matching uses the marketplace catalog only; there is no external competitor feed.</p>
      <form className="seller-advanced-form" onSubmit={save}>
        <label>Product<select required value={productId} onChange={(event) => { setProductId(event.target.value); const selected = products.find((item) => item.id === event.target.value); setMinPrice(selected?.price ?? ""); setMaxPrice(selected?.price ?? ""); }}><option value="">Select product</option>{products.map((item) => <option value={item.id} key={item.id}>{item.name} · {formatKsh(item.price)}</option>)}</select></label>
        <label>Minimum price<input required type="number" min="0.01" step="0.01" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} /></label>
        <label>Maximum price<input required type="number" min="0.01" step="0.01" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} /></label>
        <label>Rule<select value={rule} onChange={(event) => setRule(event.target.value)}><option value="CLEARANCE_DISCOUNT">Clearance discount</option><option value="MATCH_LOWEST_MARKET_PRICE">Match lowest marketplace price</option></select></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || busy || !productId}>{busy ? "Applying…" : "Save & apply rule"}</button>
      </form>
      <div className="seller-advanced-list">{rules.map((item) => <article key={item.id}><div><strong>{item.product_name} · {item.rule.replaceAll("_", " ")}</strong><small>Guard {formatKsh(item.min_price)}–{formatKsh(item.max_price)} · Applied {formatKsh(item.applied_price)}</small></div></article>)}</div>
    </section>
  );
}

function BranchManager({ products, branches, demoMode, refresh, setError, setNotice }) {
  const [branch, setBranch] = useState({ name: "", address: "", city: "Nairobi", phone: "" });
  const [allocation, setAllocation] = useState({ branch_id: "", product_id: "", quantity: 0 });

  async function addBranch(event) {
    event.preventDefault();
    try {
      await createSellerBranch(branch);
      setBranch({ name: "", address: "", city: "Nairobi", phone: "" });
      setNotice("Branch added.");
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  async function allocate(event) {
    event.preventDefault();
    try {
      await updateSellerBranchInventory(allocation.branch_id, [{ product_id: allocation.product_id, quantity: Number(allocation.quantity) }]);
      setNotice("Branch stock allocation updated.");
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">STORE LOCATIONS</span><h2>Branches &amp; stock allocation</h2></div></header>
      <form className="seller-advanced-form" onSubmit={addBranch}>
        <label>Branch name<input required minLength="2" value={branch.name} onChange={(event) => setBranch((current) => ({ ...current, name: event.target.value }))} /></label>
        <label>Address<input required minLength="5" value={branch.address} onChange={(event) => setBranch((current) => ({ ...current, address: event.target.value }))} /></label>
        <label>City<input required value={branch.city} onChange={(event) => setBranch((current) => ({ ...current, city: event.target.value }))} /></label>
        <label>Phone<input value={branch.phone} onChange={(event) => setBranch((current) => ({ ...current, phone: event.target.value }))} /></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode}>Add branch</button>
      </form>
      <form className="seller-advanced-form" onSubmit={allocate}>
        <label>Branch<select required value={allocation.branch_id} onChange={(event) => setAllocation((current) => ({ ...current, branch_id: event.target.value }))}><option value="">Choose branch</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.city}</option>)}</select></label>
        <label>Product<select required value={allocation.product_id} onChange={(event) => setAllocation((current) => ({ ...current, product_id: event.target.value }))}><option value="">Choose product</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.stock} total</option>)}</select></label>
        <label>Allocation quantity<input type="number" min="0" required value={allocation.quantity} onChange={(event) => setAllocation((current) => ({ ...current, quantity: event.target.value }))} /></label>
        <button className="marketplace-button primary" type="submit" disabled={demoMode || !allocation.branch_id || !allocation.product_id}>Save allocation</button>
      </form>
      <div className="seller-advanced-list">{branches.map((item) => <article key={item.id}><div><strong>{item.name} · {item.city}</strong><small>{item.address}</small><small>{item.inventory.map((stock) => `${stock.product_name}: ${stock.quantity}`).join(" · ") || "No stock allocated"}</small></div></article>)}</div>
    </section>
  );
}

function RestockPlanner({ plan, demoMode, refresh, setError, setNotice }) {
  async function request(item) {
    try {
      const quantity = item.recommended_quantity || Math.max(5, item.low_stock_threshold * 2 - item.stock);
      await requestSellerRestock(item.id, quantity);
      setNotice(`Restock recommendation for ${item.name} recorded; no purchase order was sent.`);
      await refresh();
    } catch (error) {
      setError(error.message);
    }
  }

  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">INVENTORY VELOCITY</span><h2>Restock planner</h2></div></header>
      <p className="seller-operation-note">Sales velocity is calculated from paid orders in the last 30 days. A restock request records a recommendation only.</p>
      <div className="seller-advanced-list">{plan.map((item) => <article key={item.id}><div><strong>{item.name} · {item.stock} in stock</strong><small>{item.units_sold_30d} sold in 30 days · {item.days_of_supply == null ? "No sales velocity" : `${item.days_of_supply} days of supply`}</small>{item.low_stock && <small className="seller-low-stock-label">Below low-stock threshold</small>}</div><button type="button" className="marketplace-button primary" disabled={demoMode || Boolean(item.latest_request)} onClick={() => request(item)}>{item.latest_request ? "Requested" : `Recommend ${item.recommended_quantity || "restock"}`}</button></article>)}</div>
    </section>
  );
}

function ReviewRequester({ orders, demoMode, setError, setNotice }) {
  const [busyOrder, setBusyOrder] = useState(null);
  async function request(order, channel) {
    setBusyOrder(order.id);
    setError("");
    try {
      const result = await requestSellerOrderReview(order.id, channel);
      setNotice(result.message);
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyOrder(null);
    }
  }
  const delivered = orders.filter((order) => order.fulfillment_status === "DELIVERED");
  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">BUYER FEEDBACK</span><h2>Automated review requests</h2></div></header>
      <p className="seller-operation-note">Review requests are audited as simulated records. No email or SMS is sent because no delivery provider is connected.</p>
      <div className="seller-advanced-list">{delivered.map((order) => <article key={order.id}><div><strong>{order.order_number}</strong><small>{order.customer.name} · {order.payment_status}</small></div><div className="seller-return-actions"><button className="marketplace-button secondary" type="button" disabled={demoMode || busyOrder === order.id} onClick={() => request(order, "EMAIL")}>Request by email</button><button className="marketplace-button secondary" type="button" disabled={demoMode || busyOrder === order.id} onClick={() => request(order, "SMS")}>Request by SMS</button></div></article>)}</div>
      {!delivered.length && <p className="marketplace-empty">Delivered orders will appear here.</p>}
    </section>
  );
}

function VendorAI({ data }) {
  return (
    <section className="seller-panel seller-operations-panel">
      <header><div><span className="marketplace-eyebrow">SELLER COPILOT</span><h2>Catalog &amp; sales insights</h2></div></header>
      <p className="seller-operation-note">{data.source || "Rule-based demo insights; no external AI model is connected."}</p>
      <div className="seller-advanced-grid">{(data.top_categories ?? []).map((item) => <article className="seller-advanced-card" key={item.category}><span>Top category</span><strong>{item.category}</strong><small>{item.units_sold_30d} units · 30 days</small></article>)}</div>
      <div className="seller-advanced-list">{(data.recommendations ?? []).map((item) => <article key={`${item.type}-${item.product_id}`}><div><strong>{item.title}</strong><small>{item.detail}</small></div></article>)}</div>
      {!data.recommendations?.length && <p className="marketplace-empty">No replenishment recommendations at this time.</p>}
    </section>
  );
}

async function loadSellerLogistics() {
  const [modes, manifests] = await Promise.all([
    fetchSellerFulfillment(),
    fetchSellerManifests(),
  ]);
  if (!Array.isArray(modes) || !Array.isArray(manifests)) {
    throw new Error("The warehouse and logistics response was invalid. Please reload this tab.");
  }
  return [modes, manifests];
}

const loaders = {
  team: fetchSellerTeam,
  messages: fetchSellerMessages,
  logistics: loadSellerLogistics,
  quality: fetchSellerQcQueue,
  statement: fetchSellerWeeklyStatement,
  repricing: fetchSellerRepricingRules,
  branches: fetchSellerBranches,
  restock: fetchSellerRestockPlan,
  insights: fetchSellerInsights,
};

export default function SellerOperations({ tab, products, orders, demoMode, onNotice }) {
  const [data, setData] = useState(null);
  const [loadedTab, setLoadedTab] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    const loader = loaders[tab];
    if (!loader) return;
    const result = await loader();
    setData(result);
    setLoadedTab(tab);
    setError("");
  }

  useEffect(() => {
    setData(null);
    setLoadedTab(null);
    setError("");
    if (demoMode || !loaders[tab]) {
      return undefined;
    }
    let active = true;
    const load = async () => {
      try {
        const result = await loaders[tab]();
        if (active) {
          setData(result);
          setLoadedTab(tab);
          setError("");
        }
      } catch (loadError) {
        if (active) {
          setData(null);
          setLoadedTab(null);
          setError(loadError.message);
        }
      }
    };
    void load();
    const timer = tab === "messages" ? window.setInterval(load, 5000) : null;
    return () => {
      active = false;
      if (timer) window.clearInterval(timer);
    };
  }, [demoMode, tab]);

  useEffect(() => {
    if (notice) {
      onNotice(notice);
      setNotice("");
    }
  }, [notice, onNotice]);

  if (demoMode) {
    return <section className="seller-panel seller-tab-content"><p className="seller-operation-note">Sign in to connect these modules to a real seller account.</p></section>;
  }

  const ready = data !== null && loadedTab === tab;
  return (
    <div className="seller-tab-content">
      {error && <p className="marketplace-error" role="alert">{error}</p>}
      {!ready && !error && <p className="seller-operation-note">Loading seller tools…</p>}
      {tab === "team" && ready && <TeamManager data={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "messages" && ready && <ChatInbox messages={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "logistics" && ready && <LogisticsManager products={products} modes={data[0]} manifests={data[1]} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "quality" && ready && <CatalogHealth products={products} queue={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "statement" && ready && <VendorStatement statement={data} />}
      {tab === "repricing" && ready && <DynamicRepricer products={products} rules={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "branches" && ready && <BranchManager products={products} branches={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "restock" && ready && <RestockPlanner plan={data} demoMode={demoMode} refresh={refresh} setError={setError} setNotice={setNotice} />}
      {tab === "reviews" && <ReviewRequester orders={orders} demoMode={demoMode} setError={setError} setNotice={setNotice} />}
      {tab === "insights" && ready && <VendorAI data={data} />}
    </div>
  );
}

export { SellerNotificationSettings };
