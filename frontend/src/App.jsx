import { memo, useEffect, useMemo, useState } from 'react';


async function fetchJson(url, options = {}, fallbackMessage = 'Request failed.') {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || data?.error || fallbackMessage);
  }
  return data;
}


function postJson(url, payload, fallbackMessage, method = 'POST') {
  return fetchJson(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, fallbackMessage);
}


function buildLineChart(values, width = 280, height = 140) {
  if (!values.length) return <div className="chart-empty">No usage data available.</div>;
  const padding = 18;
  const max = Math.max(...values);
  const points = values.map((value, index) => {
    const x = padding + (index * (width - padding * 2)) / (values.length - 1);
    const y = height - padding - (value / max) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" role="img" aria-label="Energy usage trend">
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      <polyline points={points} />
    </svg>
  );
}


function buildBarChart(values) {
  if (!values.length) return <div className="chart-empty">No usage data available.</div>;
  const max = Math.max(...values);
  return (
    <div className="bar-chart" role="img" aria-label="Daily energy consumption comparison">
      {values.map((value, index) => (
        <div className="bar-item" key={index} aria-hidden="true">
          <span className="bar-value">{value}</span>
          <div className="bar-column"><span style={{ height: `${Math.max(12, (value / max) * 100)}%` }} /></div>
          <span className="bar-label">D{index + 1}</span>
        </div>
      ))}
    </div>
  );
}


const ProfileCard = memo(function ProfileCard({ data }) {
  const profile = data.profile || {};
  const usage = Array.isArray(profile.usage) ? profile.usage : [];
  return (
    <div className="page-detail-card detail-card">
      <div className="detail-grid page-detail-grid">
        <div><p className="eyebrow">Meter ID</p><strong>{profile.meterId}</strong></div>
        <div><p className="eyebrow">Location</p><strong>{profile.location}</strong></div>
        <div><p className="eyebrow">Tariff</p><strong>{profile.tariff}</strong></div>
        <div><p className="eyebrow">Voltage</p><strong>{profile.voltage}</strong></div>
      </div>
      <div className="detail-header">
        <div><p className="eyebrow">Meter status</p><h3>{profile.status}</h3></div>
        <div className="billing-card page-billing-card">
          <p className="eyebrow">Estimated monthly bill</p><h4>${profile.billing}</h4>
        </div>
      </div>
      <div className="graph-grid page-graph-grid">
        <div className="graph-card"><h4>Usage Trend</h4>{buildLineChart(usage)}</div>
        <div className="graph-card"><h4>Daily Load</h4>{buildBarChart(usage)}</div>
      </div>
      <div className="usage-summary">
        {usage.map((value, index) => (
          <div className="usage-pill" key={`${profile.meterId}-${index}`}>
            <span>Day {index + 1}</span><strong>{value} kWh</strong>
          </div>
        ))}
      </div>
    </div>
  );
});


function UtilitiesDashboard({ data }) {
  return (
    <div className="panel wide-panel">
      <div className="page-heading">
        <div><p className="eyebrow">Utilities workspace</p><h3>Your Meter Account</h3></div>
        <span className="access-badge">Personal data only</span>
      </div>
      <p className="search-hint">Welcome back, <strong>{data.username}</strong>. This page contains only your utility account.</p>
      <ProfileCard data={data} />
    </div>
  );
}


function SalesDashboard({ data }) {
  const totalRevenue = data.records.reduce((sum, row) => sum + row.revenue, 0);
  const totalUsage = data.records.reduce((sum, row) => sum + row.usageMwh, 0);
  return (
    <div className="panel wide-panel">
      <div className="page-heading">
        <div><p className="eyebrow">Sales workspace</p><h3>{data.region} Region</h3></div>
        <span className="access-badge">Region restricted</span>
      </div>
      <div className="stat-grid">
        <div className="stat-card"><span>Accounts</span><strong>{data.records.length}</strong></div>
        <div className="stat-card"><span>Usage</span><strong>{totalUsage.toLocaleString()} MWh</strong></div>
        <div className="stat-card"><span>Revenue</span><strong>${totalRevenue.toLocaleString()}</strong></div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Customer</th><th>Utility</th><th>Usage</th><th>Revenue</th><th>Status</th></tr></thead>
          <tbody>
            {data.records.map((row) => (
              <tr key={row.id}>
                <td><strong>{row.customerName}</strong></td><td>{row.utilityType}</td>
                <td>{row.usageMwh.toLocaleString()} MWh</td><td>${row.revenue.toLocaleString()}</td>
                <td><span className="status-chip">{row.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="privacy-note">Your region is assigned by an administrator. Other regional records are blocked by the server.</p>
    </div>
  );
}


function AnalystDashboard({ data }) {
  return (
    <div className="panel wide-panel">
      <div className="page-heading">
        <div><p className="eyebrow">Business intelligence</p><h3>Regional Performance</h3></div>
        <span className="access-badge">Aggregate data only</span>
      </div>
      <div className="stat-grid">
        <div className="stat-card"><span>Total accounts</span><strong>{data.totals.accounts}</strong></div>
        <div className="stat-card"><span>Total usage</span><strong>{data.totals.usageMwh.toLocaleString()} MWh</strong></div>
        <div className="stat-card"><span>Total revenue</span><strong>${data.totals.revenue.toLocaleString()}</strong></div>
      </div>
      <div className="analytics-grid">
        {data.regions.map((region) => (
          <article className="region-card" key={region.region}>
            <p className="eyebrow">Region</p><h4>{region.region}</h4>
            <dl>
              <div><dt>Accounts</dt><dd>{region.accounts}</dd></div>
              <div><dt>Active</dt><dd>{region.activeAccounts}</dd></div>
              <div><dt>Usage</dt><dd>{region.usageMwh.toLocaleString()} MWh</dd></div>
              <div><dt>Revenue</dt><dd>${region.revenue.toLocaleString()}</dd></div>
            </dl>
          </article>
        ))}
      </div>
      <p className="privacy-note">{data.privacyNote}</p>
    </div>
  );
}


function RoleFields({ role, region, regions, onRoleChange, onRegionChange }) {
  return (
    <>
      <label>Role
        <select name="role" value={role} onChange={onRoleChange}>
          <option value="utilities">Utilities</option>
          <option value="business_analyst">Business Analyst</option>
          <option value="sales_person">Sales Person</option>
        </select>
      </label>
      {role === 'sales_person' && (
        <label>Sales region
          <select name="region" value={region} onChange={onRegionChange} required>
            {regions.map((item) => <option value={item} key={item}>{item}</option>)}
          </select>
        </label>
      )}
    </>
  );
}


function ManagedAccount({ account, regions, onSaved, onDeleted }) {
  const [role, setRole] = useState(account.role);
  const [region, setRegion] = useState(account.region || regions[0] || 'texas');
  const [saving, setSaving] = useState(false);
  const [rowMessage, setRowMessage] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  async function save(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      username: form.get('username'),
      password: form.get('password') || null,
      role,
      region: role === 'sales_person' ? region : null
    };
    setSaving(true);
    setRowMessage('');
    try {
      const result = await postJson(`/api/admin/users/${account.id}`, payload, 'Unable to update account.', 'PUT');
      setRowMessage('Saved');
      formElement.elements.password.value = '';
      onSaved(result.user);
    } catch (error) {
      setRowMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  function openDeleteDialog() {
    setDeleteConfirmation('');
    setDeleteError('');
    setDeleteOpen(true);
  }

  function closeDeleteDialog() {
    if (!deleting) setDeleteOpen(false);
  }

  async function deleteAccount() {
    if (deleteConfirmation !== 'delete') return;
    setDeleting(true);
    setDeleteError('');
    try {
      await fetchJson(`/api/admin/users/${account.id}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation: deleteConfirmation })
      }, 'Unable to delete account.');
      onDeleted(account.id);
    } catch (error) {
      setDeleteError(error.message);
      setDeleting(false);
    }
  }

  return (
    <>
      <form className="account-editor" onSubmit={save}>
        <div className="identity-summary">
          <strong>{[account.firstName, account.lastName].filter(Boolean).join(' ') || 'No Keycloak name'}</strong>
          <span>{account.email || 'No Keycloak email'} · {account.emailVerified ? 'Email verified' : 'Email not verified'}</span>
        </div>
        <label>Username<input name="username" defaultValue={account.username} required /></label>
        <RoleFields
          role={role} region={region} regions={regions}
          onRoleChange={(event) => setRole(event.target.value)}
          onRegionChange={(event) => setRegion(event.target.value)}
        />
        <label>New local password<input name="password" type="password" minLength="8" placeholder="Leave blank to keep" /></label>
        <div className="editor-action">
          <div className="editor-buttons">
            <button disabled={saving}>{saving ? 'Saving...' : 'Save changes'}</button>
            <button type="button" className="danger-btn" onClick={openDeleteDialog}>Delete user</button>
          </div>
          <span className={rowMessage === 'Saved' ? 'success-text' : 'error-text'}>{rowMessage}</span>
        </div>
      </form>

      {deleteOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeDeleteDialog();
        }}>
          <section className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby={`delete-title-${account.id}`}>
            <p className="eyebrow danger-text">Permanent action</p>
            <h3 id={`delete-title-${account.id}`}>Delete {account.username}?</h3>
            <p>
              This removes the account and this portal's Keycloak access, then signs it out
              of all portal sessions. The shared Keycloak identity and access to other websites remain unchanged.
            </p>
            <label>
              Type <strong>delete</strong> to confirm
              <input
                autoFocus
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                placeholder="delete"
                autoComplete="off"
              />
            </label>
            {deleteError && <p className="delete-error" role="alert">{deleteError}</p>}
            <div className="dialog-actions">
              <button type="button" className="ghost-btn" onClick={closeDeleteDialog} disabled={deleting}>Cancel</button>
              <button
                type="button"
                className="danger-btn danger-solid"
                disabled={deleteConfirmation !== 'delete' || deleting}
                onClick={deleteAccount}
              >
                {deleting ? 'Deleting...' : 'Confirm delete'}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}


function AdminDashboard({
  accounts, regions, keycloakManagementEnabled,
  onAccountCreated, onAccountSaved, onAccountDeleted
}) {
  const [createRole, setCreateRole] = useState('utilities');
  const [createRegion, setCreateRegion] = useState(regions[0] || 'texas');
  const [createMessage, setCreateMessage] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');
  const [accountQuery, setAccountQuery] = useState('');

  const counts = useMemo(() => accounts.reduce((result, account) => {
    result[account.role] = (result[account.role] || 0) + 1;
    return result;
  }, {}), [accounts]);

  const visibleAccounts = useMemo(() => {
    const query = accountQuery.trim().toLocaleLowerCase();
    if (!query) return accounts;
    return accounts.filter((account) => account.username.toLocaleLowerCase().includes(query));
  }, [accounts, accountQuery]);

  async function createAccount(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const result = await postJson('/api/admin/users', {
        username: form.get('username'), password: form.get('password'), role: createRole,
        email: form.get('email'), firstName: form.get('firstName'), lastName: form.get('lastName'),
        emailVerified: form.get('emailVerified') === 'on',
        region: createRole === 'sales_person' ? createRegion : null
      }, 'Unable to create account.');
      onAccountCreated(result.user);
      setCreateMessage(result.keycloak?.userCreated
        ? 'New Keycloak identity created with a temporary password and portal access granted.'
        : result.keycloak?.profileUpdated
          ? 'Existing Keycloak identity found. Missing profile details were added, portal access was granted, and existing identity data was preserved.'
          : 'Existing Keycloak identity found and portal access granted. Its shared Keycloak profile and password were preserved.');
      formElement.reset();
      setCreateRole('utilities');
    } catch (error) {
      setCreateMessage(error.message);
    }
  }

  async function reconcileKeycloakAccess() {
    setSyncing(true);
    setSyncMessage('');
    try {
      const result = await postJson(
        '/api/admin/keycloak/reconcile', {}, 'Unable to synchronize Keycloak access.'
      );
      const summary = result.summary;
      const unresolved = summary.missingInKeycloak.length + summary.staleBindings.length;
      setSyncMessage(
        `Matched ${summary.matched}; granted ${summary.accessGranted}; already granted ${summary.alreadyGranted}`
        + (unresolved ? `; ${unresolved} account(s) require review.` : '.')
      );
    } catch (error) {
      setSyncMessage(error.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="admin-layout">
      <div className="panel wide-panel">
        <div className="page-heading">
          <div><p className="eyebrow">Administrator</p><h3>Role & Credential Management</h3></div>
          <span className="access-badge">
            {keycloakManagementEnabled ? 'Keycloak synchronized' : 'Keycloak setup required'}
          </span>
        </div>
        <div className="stat-grid">
          <div className="stat-card"><span>Utilities</span><strong>{counts.utilities || 0}</strong></div>
          <div className="stat-card"><span>Analysts</span><strong>{counts.business_analyst || 0}</strong></div>
          <div className="stat-card"><span>Sales people</span><strong>{counts.sales_person || 0}</strong></div>
        </div>
      </div>

      <div className="panel wide-panel">
        <h3>Create Utilities or Role Account</h3>
        <p className="search-hint">
          Existing Keycloak identities are reused and granted access only to this portal.
          Otherwise, a new Keycloak identity is created with a temporary password.
          Username, password, email, first name, last name, and role are required;
          email verification is optional.
        </p>
        <form className="create-account-form" onSubmit={createAccount}>
          <label>Username<input name="username" minLength="3" required /></label>
          <label>Email address<input name="email" type="email" maxLength="254" required /></label>
          <label>First name<input name="firstName" maxLength="80" required /></label>
          <label>Last name<input name="lastName" maxLength="80" required /></label>
          <label>Initial/local password<input name="password" type="password" minLength="8" required /></label>
          <RoleFields
            role={createRole} region={createRegion} regions={regions}
            onRoleChange={(event) => setCreateRole(event.target.value)}
            onRegionChange={(event) => setCreateRegion(event.target.value)}
          />
          <label className="verification-toggle">
            <input name="emailVerified" type="checkbox" role="switch" />
            <span className="toggle-control" aria-hidden="true"><span /></span>
            <span className="toggle-copy"><strong>Email verified (optional)</strong><small>Mark this address verified in Keycloak</small></span>
          </label>
          <button disabled={!keycloakManagementEnabled}>Create account</button>
        </form>
        {!keycloakManagementEnabled && (
          <p className="error-text">Configure the Keycloak management service account before creating users.</p>
        )}
        <p className="inline-message">{createMessage}</p>
      </div>

      <div className="panel wide-panel">
        <div className="page-heading">
          <div>
            <h3>Existing Account Migration</h3>
            <p className="search-hint">
              Grant this portal's client role to all matching existing Keycloak identities,
              including the portal administrator.
              Missing users and stale identity links are reported without being changed.
            </p>
          </div>
          <button
            type="button"
            className="ghost-btn"
            disabled={!keycloakManagementEnabled || syncing}
            onClick={reconcileKeycloakAccess}
          >
            {syncing ? 'Synchronizing...' : 'Sync Keycloak access'}
          </button>
        </div>
        <p className="inline-message">{syncMessage}</p>
      </div>

      <div className="panel wide-panel">
        <h3>Manage Existing Accounts</h3>
        <p className="search-hint">
          Portal roles, regions, usernames, and local passwords are website-specific.
          These changes do not rename the shared Keycloak identity or change its password.
        </p>
        <div className="account-search-row">
          <label>
            Find user by username
            <input
              type="search"
              value={accountQuery}
              onChange={(event) => setAccountQuery(event.target.value)}
              placeholder="Start typing a username"
              autoComplete="off"
            />
          </label>
          <span>{visibleAccounts.length} of {accounts.length} users</span>
        </div>
        <div className="account-list">
          {visibleAccounts.map((account) => (
            <ManagedAccount
              key={account.id}
              account={account}
              regions={regions}
              onSaved={onAccountSaved}
              onDeleted={onAccountDeleted}
            />
          ))}
          {visibleAccounts.length === 0 && (
            <p className="empty-search-result">No username matches “{accountQuery.trim()}”.</p>
          )}
        </div>
      </div>
    </div>
  );
}


function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [view, setView] = useState('home');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [config, setConfig] = useState({
    regions: ['texas', 'noida', 'alpharetta', 'germany'],
    sso: { enabled: false, loginUrl: '/api/auth/sso/login' }
  });
  const keycloakLoginUrl = import.meta.env.VITE_KEYCLOAK_LOGIN_URL?.trim() || config.sso?.loginUrl;

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const ssoError = query.get('sso_error');
    if (ssoError) setMessage(ssoError);
    if (query.has('sso') || query.has('sso_error')) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    fetchJson('/api/config').then(setConfig).catch(() => {});
    fetchJson('/api/me', {}, 'Unable to restore session.')
      .then((data) => setCurrentUser(data.user))
      .catch(() => {})
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setDashboardData(null);
      setAccounts([]);
      return;
    }
    const endpoints = {
      utilities: '/api/me/profile',
      business_analyst: '/api/analytics',
      sales_person: '/api/sales/region',
      admin: '/api/admin/users'
    };
    const controller = new AbortController();
    setLoading(true);
    setMessage('');
    fetchJson(endpoints[currentUser.role], { signal: controller.signal }, 'Unable to load your dashboard.')
      .then((data) => {
        if (currentUser.role === 'admin') setAccounts(data);
        else setDashboardData(data);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setMessage(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [currentUser]);

  async function handleLogin(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const data = await postJson('/api/login', {
        username: form.get('username'), password: form.get('password')
      }, 'Login failed.');
      setCurrentUser(data.user);
      setView('home');
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    }
  }

  function handleSsoLogin() {
    setMessage('');
    if (!import.meta.env.VITE_KEYCLOAK_LOGIN_URL && !config.sso?.enabled) {
      setMessage('SSO is not configured on the backend yet. Add the Keycloak settings to backend/.env.');
      return;
    }
    try {
      const target = new URL(keycloakLoginUrl, window.location.origin);
      if (!['http:', 'https:'].includes(target.protocol)) throw new Error();
      window.location.assign(target.href);
    } catch {
      setMessage('The configured Keycloak login URL is invalid.');
    }
  }

  async function handleLogout() {
    try {
      await fetchJson('/api/logout', { method: 'POST' }, 'Unable to log out of the portal.');
      setCurrentUser(null);
      setView('home');
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    }
  }

  function handleKeycloakLogout() {
    window.location.assign('/api/auth/sso/logout');
  }

  async function handlePasswordChange(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await postJson('/api/password/change', {
        oldPassword: form.get('oldPassword'), newPassword: form.get('newPassword')
      }, 'Unable to change password.');
      setMessage('Password updated successfully.');
      formElement.reset();
    } catch (error) {
      setMessage(error.message);
    }
  }

  function updateAccount(updated) {
    setAccounts((items) => items.map((item) => item.id === updated.id ? updated : item));
  }

  if (!authChecked) return <main className="app-shell"><section className="card"><p>Loading secure portal...</p></section></main>;

  return (
    <main className="app-shell">
      {!currentUser ? (
        <section className="card auth-card">
          <div className="brand-block">
            <p className="eyebrow">Role-Based Authentication</p>
            <h1>Secure Access Portal</h1>
            <p>Sign in to your role-specific workspace.</p>
          </div>
          <form className="auth-form login-form" onSubmit={handleLogin}>
            <label>Username<input name="username" placeholder="Enter username" minLength="3" required /></label>
            <label>Password<input type="password" name="password" placeholder="Enter password" required /></label>
            <button>Sign In</button>
          </form>
          <div className="login-divider" aria-hidden="true"><span>or</span></div>
          <button type="button" className="sso-btn" onClick={handleSsoLogin}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2 4.5 5.2v5.6c0 4.8 3.1 9.2 7.5 11.2 4.4-2 7.5-6.4 7.5-11.2V5.2L12 2Zm0 3.1 4.5 1.9v3.8c0 3.3-1.8 6.5-4.5 8.1-2.7-1.6-4.5-4.8-4.5-8.1V7L12 5.1Zm0 2.9a2.6 2.6 0 0 0-2.6 2.6c0 .8.4 1.6 1 2v2.3h3.2v-2.3a2.6 2.6 0 0 0-1.6-4.6Z" />
            </svg>
            Continue with SSO
          </button>
          <p className="privacy-note">Utilities and other role accounts are created by an administrator.</p>
          <p className="message" aria-live="polite">{message}</p>
        </section>
      ) : (
        <section className="card dashboard-card">
          <header className="dashboard-header">
            <div>
              <p className="eyebrow">Signed in as</p>
              <h2>{currentUser.username} <span className="header-separator">&bull;</span> {currentUser.roleLabel}</h2>
              {currentUser.region && <p className="region-label">Assigned region: {currentUser.region}</p>}
              {currentUser.authType === 'oidc' && <span className="access-badge header-auth-badge">Keycloak SSO</span>}
            </div>
            <nav className="dashboard-actions" aria-label="Account navigation">
              <button className={view === 'home' ? '' : 'ghost-btn'} onClick={() => { setView('home'); setMessage(''); }}>Dashboard</button>
              {currentUser.authType !== 'oidc' && (
                <button className={view === 'password' ? '' : 'ghost-btn'} onClick={() => { setView('password'); setMessage(''); }}>Password</button>
              )}
              <button className="ghost-btn" onClick={handleLogout}>Log Out</button>
              {currentUser.authType === 'oidc' && (
                <button
                  className="ghost-btn keycloak-logout-btn"
                  onClick={handleKeycloakLogout}
                  title="End both the portal session and the Keycloak SSO session"
                >
                  Log Out of Keycloak
                </button>
              )}
            </nav>
          </header>

          {view === 'password' ? (
            <div className="dashboard-page">
              <div className="panel page-panel">
                <h3>Change Your Password</h3>
                <form className="auth-form" onSubmit={handlePasswordChange}>
                  <label>Current password<input type="password" name="oldPassword" required /></label>
                  <label>New password<input type="password" name="newPassword" minLength="8" required /></label>
                  <button>Update Password</button>
                </form>
              </div>
            </div>
          ) : loading ? (
            <div className="panel"><p>Loading your authorized data...</p></div>
          ) : currentUser.role === 'admin' ? (
            <AdminDashboard
              accounts={accounts} regions={config.regions}
              keycloakManagementEnabled={Boolean(config.sso?.userManagementEnabled)}
              onAccountCreated={(account) => setAccounts((items) => [...items, account])}
              onAccountSaved={updateAccount}
              onAccountDeleted={(accountId) => setAccounts((items) => items.filter((item) => item.id !== accountId))}
            />
          ) : currentUser.role === 'utilities' && dashboardData ? (
            <UtilitiesDashboard data={dashboardData} />
          ) : currentUser.role === 'sales_person' && dashboardData ? (
            <SalesDashboard data={dashboardData} />
          ) : currentUser.role === 'business_analyst' && dashboardData ? (
            <AnalystDashboard data={dashboardData} />
          ) : (
            <div className="panel"><p>Unable to load this role's dashboard.</p></div>
          )}
          <p className="message" aria-live="polite">{message}</p>
        </section>
      )}
    </main>
  );
}


export default App;
