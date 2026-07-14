import { memo, useEffect, useMemo, useRef, useState } from 'react';

async function fetchJson(url, options, fallbackMessage) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(getErrorMessage(data, fallbackMessage));
  }
  return data;
}

function postJson(url, payload, fallbackMessage) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, fallbackMessage);
}

function buildLineChart(values, width = 280, height = 140) {
  if (!values.length) {
    return (
      <div className="chart-empty" role="img" aria-label="No usage data available">
        No usage data available yet.
      </div>
    );
  }

  const padding = 18;
  const max = Math.max(...values);
  const points = values
    .map((value, index) => {
      const x = padding + (index * (width - padding * 2)) / (values.length - 1);
      const y = height - padding - (value / max) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" role="img" aria-label="Energy usage trend">
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      <polyline points={points} />
    </svg>
  );
}

function buildBarChart(values) {
  if (!values.length) {
    return (
      <div className="chart-empty" role="img" aria-label="No usage data available">
        No usage data available yet.
      </div>
    );
  }

  const max = Math.max(...values);
  return (
    <div
      className="bar-chart"
      role="img"
      aria-label={`Daily consumption comparison: ${values
        .map((value, index) => `day ${index + 1}, ${value} kilowatt-hours`)
        .join('; ')}`}
    >
      {values.map((value, index) => {
        const barHeight = Math.max(12, (value / max) * 100);
        return (
          <div className="bar-item" key={index} aria-hidden="true">
            <span className="bar-value">{value}</span>
            <div className="bar-column">
              <span style={{ height: `${barHeight}%` }} />
            </div>
            <span className="bar-label">D{index + 1}</span>
          </div>
        );
      })}
    </div>
  );
}

const ProfileCard = memo(function ProfileCard({ data }) {
  const p = data.profile || {};
  const usage = Array.isArray(p.usage) ? p.usage : [];

  return (
    <div className="page-detail-card detail-card">
      <div className="detail-grid page-detail-grid">
        <div>
          <p className="eyebrow">Meter ID</p>
          <strong>{p.meterId}</strong>
        </div>
        <div>
          <p className="eyebrow">Location</p>
          <strong>{p.location}</strong>
        </div>
        <div>
          <p className="eyebrow">Tariff</p>
          <strong>{p.tariff}</strong>
        </div>
        <div>
          <p className="eyebrow">Voltage</p>
          <strong>{p.voltage}</strong>
        </div>
      </div>

      <div className="detail-header">
        <div>
          <p className="eyebrow">Status</p>
          <h3>{p.status}</h3>
        </div>
        <div className="billing-card page-billing-card">
          <p className="eyebrow">Estimated monthly bill</p>
          <h4>${p.billing}</h4>
        </div>
      </div>

      <div className="graph-grid page-graph-grid">
        <div className="graph-card">
          <h4>Usage Trend</h4>
          {buildLineChart(usage)}
        </div>
        <div className="graph-card">
          <h4>Daily Load</h4>
          {buildBarChart(usage)}
        </div>
      </div>

      <div className="usage-summary">
        {usage.length > 0 ? usage.map((value, index) => (
          <div className="usage-pill" key={`${p.meterId}-${index}`}>
            <span>Day {index + 1}</span>
            <strong>{value} kWh</strong>
          </div>
        )) : (
          <p className="search-hint">Usage details will appear once meter data is available.</p>
        )}
      </div>
    </div>
  );
});

function getErrorMessage(responseData, fallback) {
  return responseData?.detail || responseData?.error || fallback;
}

function App() {
  const [authView, setAuthView] = useState(true);
  const [currentUser, setCurrentUser] = useState(null);
  const [view, setView] = useState('home');
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState('login');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileData, setProfileData] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUser, setSelectedUser] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const detailRequest = useRef(null);

  const settingsItems = useMemo(() => {
    const items = [
      { key: 'home', label: 'Home / Search' },
      { key: 'password', label: 'Change Password' }
    ];
    if (currentUser?.role === 'admin') {
      items.push({ key: 'create-admin', label: 'Create New Admin' });
      items.push({ key: 'promote-user', label: 'Promote Existing User' });
    }
    return items;
  }, [currentUser]);

  useEffect(() => {
    const controller = new AbortController();
    fetchJson('/api/me', { signal: controller.signal }, 'Unable to restore session.')
      .then((data) => {
        if (data.authenticated) {
          setCurrentUser(data.user);
          setAuthView(false);
          setView('home');
        }
      })
      .catch(() => {});

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setProfileData(null);
      setSearchResults([]);
      setSearchQuery('');
      setSelectedUser(null);
      setProfileLoading(false);
      setSearchLoading(false);
      return;
    }

    setMessage('');
    setSelectedUser(null);

    if (currentUser.role === 'admin') {
      setProfileData(null);
      setProfileLoading(false);
      setSearchQuery('');
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }

    const controller = new AbortController();
    setProfileLoading(true);
    fetchJson('/api/me/profile', { signal: controller.signal }, 'Unable to load profile.')
      .then((data) => {
        setProfileData(data);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setProfileData(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setProfileLoading(false);
        }
      });

    return () => controller.abort();
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser || currentUser.role !== 'admin') {
      return;
    }

    const query = searchQuery.trim();
    if (!query) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }

    const controller = new AbortController();
    setSearchLoading(true);
    const timeout = setTimeout(() => {
      fetchJson(
        `/api/users/search?q=${encodeURIComponent(query)}`,
        { signal: controller.signal },
        'Unable to search users.'
      )
        .then((data) => {
          setSearchResults(Array.isArray(data) ? data : []);
        })
        .catch((error) => {
          if (error.name !== 'AbortError') {
            setSearchResults([]);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setSearchLoading(false);
          }
        });
    }, 180);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [currentUser, searchQuery]);

  function loadUserDetail(username) {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    setSelectedUser(username);
    setProfileData(null);
    setMessage('');
    fetchJson(
      `/api/users/detail?username=${encodeURIComponent(username)}`,
      { signal: controller.signal },
      'Unable to load user details.'
    )
      .then((data) => {
        setProfileData(data);
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setMessage(error.message);
          setSelectedUser(null);
        }
      })
      .finally(() => {
        if (detailRequest.current === controller) {
          detailRequest.current = null;
        }
      });
  }

  function handleSearch(event) {
    setSearchQuery(event.target.value);
  }

  async function handleLogin(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = {
      username: formData.get('username'),
      password: formData.get('password')
    };
    try {
      const data = await postJson('/api/login', payload, 'Login failed.');
      setCurrentUser(data.user);
      setAuthView(false);
      setView('home');
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = {
      username: formData.get('username'),
      password: formData.get('password')
    };
    try {
      const data = await postJson('/api/register', payload, 'Registration failed.');
      setCurrentUser(data.user);
      setAuthView(false);
      setView('home');
      setMessage('');
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function handleLogout() {
    detailRequest.current?.abort();
    await fetch('/api/logout', { method: 'POST' });
    setCurrentUser(null);
    setAuthView(true);
    setView('home');
    setSettingsOpen(false);
    setProfileData(null);
    setSearchResults([]);
    setSearchQuery('');
    setSelectedUser(null);
  }

  async function handlePasswordChange(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = {
      oldPassword: formData.get('oldPassword'),
      newPassword: formData.get('newPassword')
    };
    try {
      await postJson('/api/password/change', payload, 'Unable to change password.');
      setMessage('Password updated successfully.');
      event.target.reset();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function handleAdminCreate(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = {
      username: formData.get('username'),
      password: formData.get('password')
    };
    try {
      await postJson('/api/admin/add', payload, 'Unable to add admin.');
      setMessage('New admin created successfully.');
      event.target.reset();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function handleAdminPromote(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = { username: formData.get('username') };
    try {
      await postJson('/api/admin/promote', payload, 'Unable to promote user.');
      setMessage('User promoted to admin successfully.');
      event.target.reset();
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <main className="app-shell">
      <section className={`card ${authView ? '' : 'hidden'}`}>
        <div className="brand-block">
          <p className="eyebrow">Role-Based Authentication</p>
          <h1>Secure Access Portal</h1>
          <p>Sign in or create an account to reach the right dashboard.</p>
        </div>

        <div className="tabs" role="tablist">
          <button className={`tab ${activeTab === 'login' ? 'active' : ''}`} onClick={() => setActiveTab('login')}>Login</button>
          <button className={`tab ${activeTab === 'register' ? 'active' : ''}`} onClick={() => setActiveTab('register')}>Register</button>
        </div>

        {activeTab === 'login' ? (
          <form className="auth-form" onSubmit={handleLogin}>
            <label>
              Username
              <input type="text" name="username" placeholder="Enter username" required />
            </label>
            <label>
              Password
              <input type="password" name="password" placeholder="Enter password" required />
            </label>
            <button type="submit">Sign In</button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleRegister}>
            <label>
              Username
              <input type="text" name="username" placeholder="Choose username" required />
            </label>
            <label>
              Password
              <input type="password" name="password" placeholder="Choose password" required />
            </label>
            <button type="submit">Create Account</button>
          </form>
        )}

        <p className="message" aria-live="polite">{message}</p>
      </section>

      <section className={`card ${authView ? 'hidden' : ''}`}>
        <div className="dashboard-header">
          <div>
            <p className="eyebrow">Signed in as</p>
            <h2>{currentUser ? `${currentUser.username} • ${currentUser.role.toUpperCase()}` : ''}</h2>
          </div>
          <div className="dashboard-actions">
            <button className="icon-btn" onClick={() => setSettingsOpen((prev) => !prev)} aria-expanded={settingsOpen}>
              ⚙️
            </button>
            <button className="ghost-btn" onClick={handleLogout}>Log Out</button>
          </div>
        </div>

        <div className={`settings-panel ${settingsOpen ? 'open' : ''}`}>
          <div className="settings-card">
            {settingsItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`settings-link ${view === item.key ? 'active' : ''}`}
                onClick={() => {
                  setView(item.key);
                  setSettingsOpen(false);
                  setMessage('');
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div id="dashboard-content">
          {view === 'password' ? (
            <div className="dashboard-page">
              <div className="panel page-panel">
                <h3>Change Password</h3>
                <form className="auth-form" onSubmit={handlePasswordChange}>
                  <label>
                    Current password
                    <input type="password" name="oldPassword" placeholder="Enter current password" required />
                  </label>
                  <label>
                    New password
                    <input type="password" name="newPassword" placeholder="Enter new password" required />
                  </label>
                  <button type="submit">Update Password</button>
                </form>
              </div>
            </div>
          ) : view === 'create-admin' ? (
            <div className="dashboard-page">
              <div className="panel page-panel">
                <h3>Create New Admin</h3>
                <form className="auth-form" onSubmit={handleAdminCreate}>
                  <label>
                    New admin username
                    <input type="text" name="username" placeholder="New admin username" required />
                  </label>
                  <label>
                    New admin password
                    <input type="password" name="password" placeholder="New admin password" required />
                  </label>
                  <button type="submit">Create Admin Account</button>
                </form>
              </div>
            </div>
          ) : view === 'promote-user' ? (
            <div className="dashboard-page">
              <div className="panel page-panel">
                <h3>Promote Existing User</h3>
                <form className="auth-form" onSubmit={handleAdminPromote}>
                  <label>
                    Existing username
                    <input type="text" name="username" placeholder="Existing username" required />
                  </label>
                  <button type="submit">Make Admin</button>
                </form>
              </div>
            </div>
          ) : (
            <div className="dashboard-home">
              {currentUser?.role === 'admin' ? (
                <div className="panel center-panel" id="home-panel">
                  <h3>Search Registered Users</h3>
                  <p className="search-hint">Find registered accounts from the secure portal.</p>
                  <label className="search-field">
                    <span>Search by username</span>
                    <input
                      id="user-search-input"
                      type="text"
                      placeholder="Type a name..."
                      autoComplete="off"
                      value={searchQuery}
                      onChange={handleSearch}
                    />
                  </label>

                  {selectedUser && profileData ? (
                    <div className="selected-user-panel">
                      <div className="selected-user-header">
                        <div>
                          <p className="eyebrow">Selected user</p>
                          <h4>{profileData.username}</h4>
                        </div>
                        <button type="button" className="ghost-btn" onClick={() => {
                          setSelectedUser(null);
                          setProfileData(null);
                        }}>
                          Back to search
                        </button>
                      </div>
                      <ProfileCard data={profileData} />
                    </div>
                  ) : (
                    <ul className="search-results">
                      {searchLoading ? (
                        <li className="search-empty">Searching users...</li>
                      ) : searchQuery.trim() && searchResults.length === 0 ? (
                        <li className="search-empty">No matching users found.</li>
                      ) : searchQuery.trim() ? (
                        searchResults.map((user) => (
                          <li key={user.username}>
                            <button type="button" className="search-result" onClick={() => loadUserDetail(user.username)}>
                              <strong>{user.username}</strong>
                              <span>{user.role}</span>
                            </button>
                          </li>
                        ))
                      ) : (
                        <li className="search-empty">Start typing to find registered users.</li>
                      )}
                    </ul>
                  )}
                </div>
              ) : profileLoading ? (
                <div className="panel center-panel"><p className="search-hint">Loading your dashboard...</p></div>
              ) : profileData ? (
                <div className="panel center-panel" id="home-panel">
                  <h3>Your Account</h3>
                  <p className="search-hint">Welcome back, <strong>{profileData.username}</strong>.</p>
                  <ProfileCard data={profileData} />
                </div>
              ) : (
                <div className="panel center-panel"><p className="search-hint">Unable to load profile.</p></div>
              )}
            </div>
          )}
        </div>
        <p className="message" aria-live="polite">{message}</p>
      </section>
    </main>
  );
}

export default App;
