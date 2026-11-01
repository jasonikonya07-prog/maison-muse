import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Download, FileJson2, RefreshCw, Search } from "lucide-react";
import {
  downloadAdminAuditLogs,
  fetchAdminAuditLogs,
} from "../../services/api.js";

const CATEGORIES = ["all", "Auth", "Inventory", "Orders", "Pricing", "Marketplace", "System"];

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", {
        dateStyle: "medium",
        timeStyle: "medium",
      }).format(date);
}

export default function AuditLogs() {
  const [filters, setFilters] = useState({
    category: "all",
    search: "",
    start_date: "",
    end_date: "",
  });
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setLogs(await fetchAdminAuditLogs(filters));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const exportLogs = async (format) => {
    setExporting(true);
    setError("");
    try {
      const blob = await downloadAdminAuditLogs(filters, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `maison-muse-audit.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setError(exportError.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="admin-panel admin-ops-panel admin-audit-panel">
      <header className="admin-panel-heading">
        <div><span className="admin-overline">APPEND-ONLY SYSTEM RECORD</span><h2>Audit log <small>{logs.length} entries</small></h2></div>
        <div className="admin-ops-toolbar">
          <button className="admin-button secondary" onClick={load} disabled={loading}><RefreshCw size={14} />Refresh</button>
          <button className="admin-button secondary" onClick={() => exportLogs("csv")} disabled={exporting}><Download size={14} />CSV</button>
          <button className="admin-button secondary" onClick={() => exportLogs("json")} disabled={exporting}><FileJson2 size={14} />JSON</button>
        </div>
      </header>

      <div className="admin-ops-filters">
        <label className="admin-table-search"><Search size={15} /><input placeholder="Search user, event, description, IP" value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} /></label>
        <select aria-label="Filter audit category" value={filters.category} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}>
          {CATEGORIES.map((category) => <option value={category} key={category}>{category === "all" ? "All categories" : category}</option>)}
        </select>
        <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilters((current) => ({ ...current, start_date: event.target.value }))} /></label>
        <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilters((current) => ({ ...current, end_date: event.target.value }))} /></label>
      </div>

      {error && <div className="admin-ops-error" role="alert"><AlertTriangle size={16} />{error}</div>}
      <p className="admin-ops-note">Audit entries are stored server-side. The database rejects update/delete operations on existing log entries.</p>
      <div className="admin-table-scroll">
        <table className="admin-table admin-ops-table admin-audit-table">
          <thead><tr><th>Timestamp</th><th>Admin</th><th>Category</th><th>Event</th><th>Description</th><th>IP address</th><th>Severity</th></tr></thead>
          <tbody>{logs.map((log) => (
            <tr key={log.id}>
              <td>{formatTime(log.occurred_at)}</td>
              <td><strong>{log.admin_username}</strong></td>
              <td>{log.event_category}</td>
              <td><code>{log.event_type}</code></td>
              <td>{log.description}</td>
              <td>{log.ip_address}</td>
              <td><span className={`admin-ops-severity ${log.severity.toLowerCase()}`}>{log.severity}</span></td>
            </tr>
          ))}
          {!logs.length && <tr><td className="admin-empty-copy" colSpan="7">{loading ? "Loading audit entries…" : "No audit entries match these filters."}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
