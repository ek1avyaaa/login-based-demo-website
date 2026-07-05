const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const app = express();
const port = process.env.PORT || 3000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
// During development ensure JS files are not cached by the browser
app.use((req, res, next) => {
  if (req.path.endsWith('.js')) {
    res.setHeader('Cache-Control', 'no-store, must-revalidate');
  }
  next();
});
app.use(express.static(path.join(__dirname, 'public')));
app.use(
  session({
    secret: 'role-dashboard-secret',
    resave: false,
    saveUninitialized: false,
    cookie: { secure: false }
  })
);

const db = new sqlite3.Database(path.join(__dirname, 'users.db'));

function initializeDatabase() {
  db.serialize(() => {
    db.run(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
      )
    `);

    const adminHash = bcrypt.hashSync('Eklavya@123', 10);

    db.run(
      'INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)',
      ['eklavya', adminHash, 'admin']
    );
    db.run('UPDATE users SET role = ?, password = ? WHERE username = ?', ['admin', adminHash, 'eklavya']);
  });
}

function getUserByUsername(username) {
  return new Promise((resolve, reject) => {
    db.get('SELECT * FROM users WHERE username = ?', [username], (err, row) => {
      if (err) {
        reject(err);
      } else {
        resolve(row);
      }
    });
  });
}

function createUser(username, password, role) {
  return new Promise((resolve, reject) => {
    const hashedPassword = bcrypt.hashSync(password, 10);
    db.run(
      'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
      [username, hashedPassword, role],
      function (err) {
        if (err) {
          reject(err);
        } else {
          resolve({ id: this.lastID, username, role });
        }
      }
    );
  });
}

initializeDatabase();

app.get('/api/me', (req, res) => {
  if (!req.session.user) {
    return res.status(401).json({ authenticated: false });
  }

  res.json({ authenticated: true, user: req.session.user });
});

app.post('/api/login', async (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required.' });
  }

  try {
    const user = await getUserByUsername(username);
    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials.' });
    }

    const passwordMatches = bcrypt.compareSync(password, user.password);
    if (!passwordMatches) {
      return res.status(401).json({ error: 'Invalid credentials.' });
    }

    req.session.user = { id: user.id, username: user.username, role: user.role };
    res.json({ success: true, user: req.session.user });
  } catch (error) {
    res.status(500).json({ error: 'Unable to log in at the moment.' });
  }
});

app.post('/api/register', async (req, res) => {
  const { username, password } = req.body;
  const role = 'user';

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required.' });
  }

  try {
    const existingUser = await getUserByUsername(username);
    if (existingUser) {
      return res.status(409).json({ error: 'That username is already taken.' });
    }

    const user = await createUser(username, password, role);
    req.session.user = { id: user.id, username: user.username, role: user.role };
    res.status(201).json({ success: true, user: req.session.user });
  } catch (error) {
    res.status(500).json({ error: 'Unable to create the account right now.' });
  }
});

app.post('/api/admin/add', async (req, res) => {
  if (!req.session.user || req.session.user.role !== 'admin') {
    return res.status(403).json({ error: 'Only admins can add new admins.' });
  }

  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required.' });
  }

  try {
    const existingUser = await getUserByUsername(username);
    if (existingUser) {
      return res.status(409).json({ error: 'That username already exists. Use the promote option for an existing user.' });
    }

    const user = await createUser(username, password, 'admin');
    res.status(201).json({ success: true, user });
  } catch (error) {
    res.status(500).json({ error: 'Unable to create a new admin right now.' });
  }
});

app.post('/api/admin/promote', async (req, res) => {
  if (!req.session.user || req.session.user.role !== 'admin') {
    return res.status(403).json({ error: 'Only admins can promote users.' });
  }

  const { username } = req.body;

  if (!username) {
    return res.status(400).json({ error: 'Username is required.' });
  }

  try {
    const existingUser = await getUserByUsername(username);
    if (!existingUser) {
      return res.status(404).json({ error: 'User not found. Use the create-new-admin form instead.' });
    }

    if (existingUser.role === 'admin') {
      return res.status(409).json({ error: 'That user is already an admin.' });
    }

    db.run('UPDATE users SET role = ? WHERE username = ?', ['admin', username], function (err) {
      if (err) {
        return res.status(500).json({ error: 'Unable to promote the user right now.' });
      }
      res.json({ success: true, user: { username, role: 'admin' } });
    });
  } catch (error) {
    res.status(500).json({ error: 'Unable to promote the user right now.' });
  }
});

app.post('/api/password/change', async (req, res) => {
  if (!req.session.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { oldPassword, newPassword } = req.body;
  const username = req.session.user.username;

  if (!oldPassword || !newPassword) {
    return res.status(400).json({ error: 'Old and new passwords are required.' });
  }

  try {
    const user = await getUserByUsername(username);
    if (!user) {
      return res.status(404).json({ error: 'User not found.' });
    }

    const passwordMatches = bcrypt.compareSync(oldPassword, user.password);
    if (!passwordMatches) {
      return res.status(401).json({ error: 'Invalid credentials.' });
    }

    const hashedPassword = bcrypt.hashSync(newPassword, 10);
    db.run('UPDATE users SET password = ? WHERE username = ?', [hashedPassword, username], (err) => {
      if (err) {
        return res.status(500).json({ error: 'Unable to update password right now.' });
      }
      res.json({ success: true });
    });
  } catch (error) {
    res.status(500).json({ error: 'Unable to update password.' });
  }
});

function getMeterProfile(username) {
  const seed = username.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const locations = ['Oslo', 'Berlin', 'Dubai', 'Toronto', 'Singapore', 'Auckland', 'Stockholm', 'Zurich'];
  const usage = [
    32 + (seed % 14),
    28 + (seed % 12),
    36 + (seed % 15),
    41 + (seed % 13),
    46 + (seed % 16),
    52 + (seed % 14)
  ];
  const bill = 40 + (seed % 25) + usage[5] * 0.9;

  return {
    meterId: `LG-${(1000 + (seed % 9000)).toString().padStart(4, '0')}`,
    location: `${locations[seed % locations.length]} • Grid Node`,
    status: 'Online',
    usage,
    billing: bill.toFixed(2),
    tariff: 'TOU • Peak Saver',
    voltage: `${218 + (seed % 12)}V`
  };
}

app.get('/api/users/search', (req, res) => {
  if (!req.session.user || req.session.user.role !== 'admin') {
    return res.status(403).json({ error: 'Forbidden' });
  }

  const term = (req.query.q || '').toString().trim();
  if (!term) {
    return res.json([]);
  }

  const pattern = `${term.toLowerCase()}%`;
  db.all(
    'SELECT id, username, role FROM users WHERE username != ? AND LOWER(username) LIKE ? ORDER BY username LIMIT 10',
    [req.session.user.username, pattern],
    (err, rows) => {
      if (err) {
        return res.status(500).json({ error: 'Unable to search users right now.' });
      }
      res.json(rows);
    }
  );
});

app.get('/api/users/detail', (req, res) => {
  if (!req.session.user || req.session.user.role !== 'admin') {
    return res.status(403).json({ error: 'Forbidden' });
  }

  const username = (req.query.username || '').toString().trim();
  if (!username) {
    return res.status(400).json({ error: 'Username is required.' });
  }

  db.get('SELECT id, username, role FROM users WHERE username = ?', [username], (err, user) => {
    if (err) {
      return res.status(500).json({ error: 'Unable to load user details.' });
    }
    if (!user) {
      return res.status(404).json({ error: 'User not found.' });
    }

    const profile = getMeterProfile(user.username);
    res.json({ ...user, profile });
  });
});

// Return the logged-in user's own profile (no admin required)
app.get('/api/me/profile', (req, res) => {
  if (!req.session.user) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const username = req.session.user.username;
  db.get('SELECT id, username, role FROM users WHERE username = ?', [username], (err, user) => {
    if (err) {
      return res.status(500).json({ error: 'Unable to load profile.' });
    }
    if (!user) {
      return res.status(404).json({ error: 'User not found.' });
    }
    const profile = getMeterProfile(user.username);
    res.json({ ...user, profile });
  });
});

app.post('/api/logout', (req, res) => {
  req.session.destroy(() => {
    res.json({ success: true });
  });
});

app.get('*', (req, res) => {
  if (req.path.startsWith('/api/')) {
    return res.status(404).json({ error: 'Route not found.' });
  }
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(port, () => {
  console.log(`Authentication portal running at http://localhost:${port}`);
});
