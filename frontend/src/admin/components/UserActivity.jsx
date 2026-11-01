import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, Search, Users } from "lucide-react";
import { fetchAdminUserActivity } from "../../services/api.js";

function formatTime(value) {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-KE", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export default function UserActivity() {
  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setUsers(await fetchAdminUserActivity(query));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="admin-panel admin-data-panel">
      <header className="admin-panel-heading">
        <div>
          <span className="admin-overline">ACCOUNT ACCESS</span>
          <h2>User &amp; login activity <small>{users.length} accounts</small></h2>
        </div>
        <div className="admin-table-tools">
          <label className="admin-table-search">
            <Search size={15} />
            <input
              aria-label="Search users"
              placeholder="Search name, email, role, or store"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <button className="admin-button secondary" type="button" onClick={load}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </header>
      <p className="admin-ops-status-muted">
        Successful sign-ins are recorded for password and Google accounts. Failed
        sign-ins remain in Security &amp; access.
      </p>
      {error && <p className="admin-ops-error" role="alert">{error}</p>}
      {loading ? (
        <p className="admin-empty-copy">Loading account activity…</p>
      ) : (
        <div className="admin-table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Type / store</th>
                <th>Joined</th>
                <th>Successful logins</th>
                <th>Last sign-in</th>
                <th>Orders</th>
                <th>Last order</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <span className="admin-customer-cell">
                      <span className="admin-order-avatar">
                        {(user.name || user.email).slice(0, 1).toUpperCase()}
                      </span>
                      <span><strong>{user.name || "Unnamed account"}</strong><small>{user.email}</small></span>
                    </span>
                  </td>
                  <td>
                    <strong>{user.role}</strong>
                    {user.store_name && <small className="admin-stock-threshold">{user.store_name}</small>}
                  </td>
                  <td>{formatTime(user.created_at)}</td>
                  <td><span><Activity size={14} /> {user.login_count}</span></td>
                  <td>
                    {formatTime(user.last_login_at)}
                    {user.last_login_provider && (
                      <small className="admin-stock-threshold">{user.last_login_provider}</small>
                    )}
                  </td>
                  <td>{user.order_count}</td>
                  <td>{formatTime(user.last_order_at)}</td>
                </tr>
              ))}
              {!users.length && (
                <tr>
                  <td colSpan="7" className="admin-empty-copy">
                    <Users size={16} /> No accounts match this search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
