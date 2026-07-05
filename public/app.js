const authView = document.getElementById('auth-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const messageBox = document.getElementById('message');
const welcomeName = document.getElementById('welcome-name');
const dashboardContent = document.getElementById('dashboard-content');
const logoutButton = document.getElementById('logout-btn');
const tabs = document.querySelectorAll('.tab');
let userSearchTimeout;
let currentUser = null;
let activeDashboardView = 'home';


async function hydrateSession() {
  try {
    const response = await fetch('/api/me');
    const data = await response.json();
    if (data.authenticated) {
      renderDashboard(data.user);
    } else {
      showAuthView();
    }
  } catch (error) {
    showAuthView();
  }
}

function showAuthView() {
  authView.classList.remove('hidden');
  dashboardView.classList.add('hidden');
}

function attachAdminForms() {
  const addAdminForm = document.getElementById('admin-add-form');
  const adminAddMessage = document.getElementById('admin-add-message');
  const promoteForm = document.getElementById('admin-promote-form');
  const promoteMessage = document.getElementById('admin-promote-message');

  if (addAdminForm) {
    addAdminForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      adminAddMessage.textContent = '';

      const formData = new FormData(addAdminForm);
      const payload = {
        username: formData.get('username'),
        password: formData.get('password')
      };

      try {
        const response = await fetch('/api/admin/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'Unable to add admin.');
        }
        adminAddMessage.textContent = 'New admin created successfully.';
        addAdminForm.reset();
      } catch (error) {
        adminAddMessage.textContent = error.message;
      }
    });
  }

  if (promoteForm) {
    promoteForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      promoteMessage.textContent = '';

      const formData = new FormData(promoteForm);
      const payload = {
        username: formData.get('username')
      };

      try {
        const response = await fetch('/api/admin/promote', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'Unable to promote user.');
        }
        promoteMessage.textContent = 'User promoted to admin successfully.';
        promoteForm.reset();
      } catch (error) {
        promoteMessage.textContent = error.message;
      }
    });
  }
}

function attachPasswordChange() {
  const passwordForm = document.getElementById('password-change-form');
  const passwordMessage = document.getElementById('password-change-message');
  if (!passwordForm) return;

  passwordForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    passwordMessage.textContent = '';

    const formData = new FormData(passwordForm);
    const payload = {
      oldPassword: formData.get('oldPassword'),
      newPassword: formData.get('newPassword')
    };

    try {
      const response = await fetch('/api/password/change', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to change password.');
      }
      passwordMessage.textContent = 'Password updated successfully.';
      passwordForm.reset();
    } catch (error) {
      passwordMessage.textContent = error.message;
    }
  });
}

function attachSettingsToggle() {
  const settingsButton = document.getElementById('settings-btn');
  const settingsPanel = document.getElementById('settings-panel');
  if (!settingsButton || !settingsPanel) return;

  settingsButton.addEventListener('click', () => {
    const isHidden = settingsPanel.classList.contains('hidden');
    if (isHidden) {
      // populate and animate open
      renderSettingsPanel();
      settingsPanel.classList.remove('hidden');
      // force a frame then add 'open' to trigger transition
      requestAnimationFrame(() => settingsPanel.classList.add('open'));
      settingsButton.setAttribute('aria-expanded', 'true');
    } else {
      // animate close then hide after transition
      settingsPanel.classList.remove('open');
      settingsButton.setAttribute('aria-expanded', 'false');
      const onEnd = () => {
        settingsPanel.classList.add('hidden');
        settingsPanel.removeEventListener('transitionend', onEnd);
        // clear innerHTML so items don't appear until reopened
        settingsPanel.innerHTML = '';
      };
      settingsPanel.addEventListener('transitionend', onEnd);
    }
  });
}

function renderSettingsPanel() {
  const settingsPanel = document.getElementById('settings-panel');
  if (!settingsPanel) return;

  // Only show admin-specific options when the current user is an admin
  const items = [
    { key: 'home', label: 'Home / Search' },
    { key: 'password', label: 'Change Password' }
  ];
  if (currentUser && currentUser.role === 'admin') {
    items.push({ key: 'create-admin', label: 'Create New Admin' });
    items.push({ key: 'promote-user', label: 'Promote Existing User' });
  }

  settingsPanel.innerHTML = `
    <div class="settings-card">
      ${items
        .map(
          (item) => `
            <button
              type="button"
              class="settings-link ${activeDashboardView === item.key ? 'active' : ''}"
              data-view="${item.key}"
            >
              ${item.label}
            </button>
          `
        )
        .join('')}
    </div>
  `;

  settingsPanel.querySelectorAll('.settings-link').forEach((button) => {
    button.addEventListener('click', () => {
      activeDashboardView = button.dataset.view;
      renderDashboardPage(currentUser);
      settingsPanel.classList.add('hidden');
      const settingsButton = document.getElementById('settings-btn');
      if (settingsButton) {
        settingsButton.setAttribute('aria-expanded', 'false');
      }
    });
  });
}

function renderDashboardPage(user) {
  if (!user) return;

  if (activeDashboardView === 'password') {
    dashboardContent.innerHTML = `
      <div class="dashboard-page">
        <div class="panel page-panel">
          <h3>Change Password</h3>
          <form id="password-change-form" class="auth-form">
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
          <p id="password-change-message" class="message"></p>
        </div>
      </div>
    `;
    attachPasswordChange();
    return;
  }

  if (activeDashboardView === 'create-admin') {
    dashboardContent.innerHTML = `
      <div class="dashboard-page">
        <div class="panel page-panel">
          <h3>Create New Admin</h3>
          <form id="admin-add-form" class="auth-form">
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
          <p id="admin-add-message" class="message"></p>
        </div>
      </div>
    `;
    attachAdminForms();
    return;
  }

  if (activeDashboardView === 'promote-user') {
    dashboardContent.innerHTML = `
      <div class="dashboard-page">
        <div class="panel page-panel">
          <h3>Promote Existing User</h3>
          <form id="admin-promote-form" class="auth-form">
            <label>
              Existing username
              <input type="text" name="username" placeholder="Existing username" required />
            </label>
            <button type="submit">Make Admin</button>
          </form>
          <p id="admin-promote-message" class="message"></p>
        </div>
      </div>
    `;
    attachAdminForms();
    return;
  }

  dashboardContent.innerHTML = `
    <div class="dashboard-home">
      <div class="panel center-panel" id="home-panel">
      </div>
    </div>
  `;
  // render based on role: admin sees search, normal user sees own profile
  const homePanel = document.getElementById('home-panel');
  if (user.role === 'admin') {
    homePanel.innerHTML = `
      <h3>Search Registered Users</h3>
      <p class="search-hint">Find registered accounts from the secure portal.</p>
      <label class="search-field">
        <span>Search by username</span>
        <input id="user-search-input" type="text" placeholder="Type a name..." autocomplete="off" />
      </label>
      <ul id="user-search-results" class="search-results">
        <li class="search-empty">Start typing to find registered users.</li>
      </ul>
    `;
    attachUserSearch();
  } else {
    // fetch and display own profile using the full detail renderer (with charts)
    homePanel.innerHTML = '<p class="search-hint">Loading your profile...</p>';
    (async () => {
      try {
        const resp = await fetch('/api/me/profile');
        if (!resp.ok) throw new Error('Unable to load profile.');
        const data = await resp.json();
        renderUserDetail(data, homePanel);
      } catch (err) {
        homePanel.innerHTML = '<p class="search-hint">Unable to load profile.</p>';
      }
    })();
  }
}

function attachUserSearch() {
  const searchInput = document.getElementById('user-search-input');
  const resultsList = document.getElementById('user-search-results');

  if (!searchInput || !resultsList) {
    return;
  }

  searchInput.addEventListener('input', () => {
    const query = searchInput.value.trim();
    clearTimeout(userSearchTimeout);

    if (!query) {
      resultsList.innerHTML = '<li class="search-empty">Start typing to find registered users.</li>';
      return;
    }

    resultsList.innerHTML = '<li class="search-empty">Searching...</li>';

    userSearchTimeout = setTimeout(async () => {
      try {
        const response = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`);
        const users = await response.json();

        if (!response.ok) {
          throw new Error('Unable to search users.');
        }

        if (!users.length) {
          resultsList.innerHTML = '<li class="search-empty">No matching users found.</li>';
          return;
        }

        resultsList.innerHTML = users
          .map(
            (user) => `
              <li>
                <button type="button" class="search-result" data-username="${user.username}">
                  <strong>${user.username}</strong>
                  <span>${user.role}</span>
                </button>
              </li>
            `
          )
          .join('');

        resultsList.querySelectorAll('.search-result').forEach((button) => {
          button.addEventListener('click', () => {
            window.location.href = `/user.html?username=${encodeURIComponent(button.dataset.username)}`;
          });
        });
      } catch (error) {
        resultsList.innerHTML = '<li class="search-empty">Unable to load results.</li>';
      }
    }, 150);
  });
}

function buildLineChart(values, width = 280, height = 140) {
  const padding = 18;
  const max = Math.max(...values);
  const points = values
    .map((value, index) => {
      const x = padding + (index * (width - padding * 2)) / (values.length - 1);
      const y = height - padding - (value / max) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  return `
    <svg viewBox="0 0 ${width} ${height}" class="chart-svg" role="img" aria-label="Energy usage trend">
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" />
      <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" />
      <polyline points="${points}" />
    </svg>
  `;
}

function buildBarChart(values) {
  const max = Math.max(...values);
  return `
    <div class="bar-chart" role="img" aria-label="Daily consumption comparison">
      ${values
        .map((value) => {
          const barHeight = Math.max(12, (value / max) * 100);
          return `<div class="bar-column"><span style="height:${barHeight}%"></span></div>`;
        })
        .join('')}
    </div>
  `;
}

function renderUserDetail(data, container) {
  const p = data.profile || {};
  container.innerHTML = `
    <h3>Your Account</h3>
    <p class="search-hint">Welcome back, <strong>${data.username}</strong>.</p>
    <div class="page-detail-card detail-card">
      <div class="detail-grid page-detail-grid">
        <div>
          <p class="eyebrow">Meter ID</p>
          <strong>${p.meterId}</strong>
        </div>
        <div>
          <p class="eyebrow">Location</p>
          <strong>${p.location}</strong>
        </div>
        <div>
          <p class="eyebrow">Tariff</p>
          <strong>${p.tariff}</strong>
        </div>
        <div>
          <p class="eyebrow">Voltage</p>
          <strong>${p.voltage}</strong>
        </div>
      </div>

      <div class="detail-header">
        <div>
          <p class="eyebrow">Status</p>
          <h3>${p.status}</h3>
        </div>
        <div class="billing-card page-billing-card">
          <p class="eyebrow">Estimated monthly bill</p>
          <h4>$${p.billing}</h4>
        </div>
      </div>

      <div class="graph-grid page-graph-grid">
        <div class="graph-card">
          <h4>Usage Trend</h4>
          ${buildLineChart(p.usage)}
        </div>
        <div class="graph-card">
          <h4>Daily Load</h4>
          ${buildBarChart(p.usage)}
        </div>
      </div>
    </div>
  `;
}

function renderDashboard(user) {
  authView.classList.add('hidden');
  dashboardView.classList.remove('hidden');
  welcomeName.textContent = `${user.username} • ${user.role.toUpperCase()}`;

  currentUser = user;
  activeDashboardView = 'home';

  renderDashboardPage(user);
  attachSettingsToggle();
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    tabs.forEach((item) => item.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.target;
    document.getElementById('login-form').classList.toggle('hidden', target !== 'login');
    document.getElementById('register-form').classList.toggle('hidden', target !== 'register');
    messageBox.textContent = '';
  });
});

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(loginForm);
  const payload = {
    username: formData.get('username'),
    password: formData.get('password')
  };

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Login failed.');
    }
    renderDashboard(data.user);
  } catch (error) {
    messageBox.textContent = error.message;
  }
});

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(registerForm);
  const payload = {
    username: formData.get('username'),
    password: formData.get('password'),
    role: formData.get('role')
  };

  try {
    const response = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Registration failed.');
    }
    renderDashboard(data.user);
  } catch (error) {
    messageBox.textContent = error.message;
  }
});

logoutButton.addEventListener('click', async () => {
  try {
    await fetch('/api/logout', { method: 'POST' });
    showAuthView();
    loginForm.reset();
    registerForm.reset();
  } catch (error) {
    messageBox.textContent = 'Unable to log out.';
  }
});

hydrateSession();
