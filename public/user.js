function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) || '';
}

function buildLineChart(values) {
  const width = 280;
  const height = 140;
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

function renderDetailPage(user) {
  const title = document.getElementById('detail-title');
  const detailContent = document.getElementById('detail-content');

  title.textContent = `${user.username} • ${user.role.toUpperCase()}`;
  detailContent.innerHTML = `
    <div class="detail-card page-detail-card">
      <div class="detail-grid page-detail-grid">
        <div>
          <p class="eyebrow">Meter ID</p>
          <strong>${user.profile.meterId}</strong>
        </div>
        <div>
          <p class="eyebrow">Location</p>
          <strong>${user.profile.location}</strong>
        </div>
        <div>
          <p class="eyebrow">Tariff</p>
          <strong>${user.profile.tariff}</strong>
        </div>
        <div>
          <p class="eyebrow">Voltage</p>
          <strong>${user.profile.voltage}</strong>
        </div>
      </div>

      <div class="detail-header">
        <div>
          <p class="eyebrow">Status</p>
          <h3>${user.profile.status}</h3>
        </div>
        <div class="billing-card page-billing-card">
          <p class="eyebrow">Estimated monthly bill</p>
          <h4>$${user.profile.billing}</h4>
        </div>
      </div>

      <div class="graph-grid page-graph-grid">
        <div class="graph-card">
          <h4>Usage Trend</h4>
          ${buildLineChart(user.profile.usage)}
        </div>
        <div class="graph-card">
          <h4>Daily Load</h4>
          ${buildBarChart(user.profile.usage)}
        </div>
      </div>
    </div>
  `;
}

function showError(message) {
  document.getElementById('detail-message').textContent = message;
}

async function loadUserDetails() {
  const username = getQueryParam('username');
  if (!username) {
    showError('No user specified.');
    return;
  }

  try {
    const response = await fetch(`/api/users/detail?username=${encodeURIComponent(username)}`);
    const data = await response.json();
    if (!response.ok) {
      showError(data.error || 'Unable to load user details.');
      return;
    }
    renderDetailPage(data);
  } catch (error) {
    showError('Unable to load user details.');
  }
}

document.getElementById('back-btn').addEventListener('click', () => {
  window.location.href = '/';
});

loadUserDetails();
