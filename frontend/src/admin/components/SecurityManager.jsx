import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  KeyRound,
  RefreshCw,
  Shield,
  ShieldAlert,
  Smartphone,
} from "lucide-react";
import {
  fetchAdminRoles,
  fetchAdminSecurityAlerts,
  fetchAdminSessions,
  revokeAdminSession,
  updateAdminRole,
} from "../../services/api.js";

const RIGHTS = ["read", "write", "delete"];
const AREAS = ["products", "orders", "analytics", "settings"];

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export default function SecurityManager({
  adminRole = "Super Admin",
  canManageSessions = false,
}) {
  const [sessions, setSessions] = useState([]);
  const [roles, setRoles] = useState([]);
  const [alerts, setAlerts] = useState({ failed_logins: [], events: [] });
  const [error, setError] = useState("");
  const [savedRole, setSavedRole] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [sessionRows, roleRows, securityAlerts] = await Promise.all([
        fetchAdminSessions(),
        fetchAdminRoles(),
        fetchAdminSecurityAlerts(),
      ]);
      setSessions(sessionRows);
      setRoles(roleRows);
      setAlerts(securityAlerts);
    } catch (loadError) {
      setError(loadError.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const updatePermission = (roleName, area, right, checked) => {
    setRoles((current) =>
      current.map((role) =>
        role.role === roleName
          ? {
              ...role,
              permissions: {
                ...role.permissions,
                [area]: { ...role.permissions[area], [right]: checked },
              },
            }
          : role,
      ),
    );
  };

  const saveRole = async (role) => {
    setBusy(true);
    setError("");
    setSavedRole("");
    try {
      const result = await updateAdminRole(role.role, role.permissions);
      setRoles((current) =>
        current.map((item) =>
          item.role === role.role ? { ...item, permissions: result.permissions } : item,
        ),
      );
      setSavedRole(role.role);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (session) => {
    if (!window.confirm(`Revoke the ${session.role} session from ${session.ip_address}?`)) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await revokeAdminSession(session.session_id);
      await load();
    } catch (revokeError) {
      setError(revokeError.message);
    } finally {
      setBusy(false);
    }
  };

  const isSuperAdmin = adminRole === "Super Admin";
  const securityEvents = [
    ...alerts.failed_logins.map((event) => ({
      ...event,
      event_type: "Failed sign-in attempts",
      occurred_at: event.latest,
      event_category: "Auth",
    })),
    ...alerts.events,
  ];

  return (
    <div className="admin-ops-stack">
      {error && <div className="admin-ops-error" role="alert"><AlertTriangle size={16} />{error}</div>}
      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">IDENTITY & ACCESS</span><h2>Active admin sessions <small>{sessions.length} active</small></h2></div>
          <button className="admin-button secondary" onClick={load} disabled={busy}><RefreshCw size={14} /> Refresh</button>
        </header>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table">
            <thead><tr><th>Session ID</th><th>Admin</th><th>Role</th><th>IP address</th><th>Device</th><th>Last active</th><th>Action</th></tr></thead>
            <tbody>{sessions.map((session) => (
              <tr key={session.session_id}>
                <td><code>{session.session_id.slice(0, 12)}…</code></td>
                <td><strong>{session.username}</strong></td>
                <td>{session.role}</td>
                <td>{session.ip_address}</td>
                <td><span className="admin-ops-inline-icon"><Smartphone size={13} />{session.device_type}</span></td>
                <td>{formatTime(session.last_active_at)}</td>
                <td><button className="admin-button danger small" onClick={() => revoke(session)} disabled={busy || !canManageSessions}>Revoke</button></td>
              </tr>
            ))}
            {!sessions.length && <tr><td colSpan="7" className="admin-empty-copy">No active administrator sessions were found.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">LEAST-PRIVILEGE ACCESS</span><h2>Role permission matrix</h2></div>
          <span className="admin-ops-inline-icon"><KeyRound size={15} />Current role: {adminRole}</span>
        </header>
        <p className="admin-ops-note">Permissions are checked by the API on every protected request. The configured admin account is assigned through <code>ADMIN_ROLE</code>; this screen does not create user accounts.</p>
        <div className="admin-table-scroll">
          <table className="admin-table admin-ops-table admin-rbac-table">
            <thead><tr><th>Role</th>{AREAS.map((area) => <th key={area} colSpan="3">{area}</th>)}<th>Save</th></tr><tr><th /><>{AREAS.map((area) => RIGHTS.map((right) => <th className="admin-rbac-right" key={`${area}-${right}`}>{right}</th>))}</><th /></tr></thead>
            <tbody>{roles.map((role) => (
              <tr key={role.role}>
                <td><strong>{role.role}</strong></td>
                {AREAS.flatMap((area) => RIGHTS.map((right) => (
                  <td className="admin-rbac-check" key={`${role.role}-${area}-${right}`}>
                    <input
                      type="checkbox"
                      aria-label={`${role.role} ${area} ${right}`}
                      checked={Boolean(role.permissions[area]?.[right])}
                      disabled={!isSuperAdmin || busy || role.role === "Super Admin"}
                      onChange={(event) => updatePermission(role.role, area, right, event.target.checked)}
                    />
                  </td>
                )))}
                <td><button className="admin-button secondary small" disabled={!isSuperAdmin || busy} onClick={() => saveRole(role)}><Check size={13} />Save</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        {savedRole && <p className="admin-ops-success" role="status">{savedRole} permissions saved.</p>}
        {!isSuperAdmin && <p className="admin-ops-note">Only Super Admin can change role permissions.</p>}
      </section>

      <section className="admin-panel admin-ops-panel">
        <header className="admin-panel-heading">
          <div><span className="admin-overline">THREAT MONITORING · LAST 24 HOURS</span><h2>Security alerts</h2></div>
          <ShieldAlert size={19} className="admin-ops-rose-icon" />
        </header>
        <div className="admin-ops-alert-list">
          {securityEvents.map((event, index) => (
            <article className={`admin-ops-alert ${event.severity === "CRITICAL" ? "critical" : "warning"}`} key={`${event.event_type}-${event.id ?? index}`}>
              <span className="admin-ops-alert-icon">{event.severity === "CRITICAL" ? <ShieldAlert size={16} /> : <AlertTriangle size={16} />}</span>
              <span><strong>{event.message ?? event.description ?? event.event_type}</strong><small>{event.event_category} · {event.admin_username ?? "Unknown"} · {event.ip_address} · {formatTime(event.occurred_at)}</small></span>
              <b>{event.severity}</b>
            </article>
          ))}
          {!securityEvents.length && <p className="admin-empty-copy">No security alerts in the last 24 hours.</p>}
        </div>
      </section>
    </div>
  );
}
