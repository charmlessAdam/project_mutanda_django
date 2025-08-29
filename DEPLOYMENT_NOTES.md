# 🚀 Django Lightsail Deployment - TODO Notes

## ✅ What's Working Now
- ✅ GitHub Actions automated deployment from **public** repository
- ✅ Django API running on http://18.197.254.230:8080
- ✅ All API endpoints functional (`/api/`, `/admin/`, `/api/medicine/`, `/api/token/`)
- ✅ Automatic code deployment on git push to main branch
- ✅ Dependencies auto-install, migrations auto-run

## 🔧 Priority Tasks to Implement Later

### 1. 🔒 SSL Certificate Setup (FREE)
**Goal:** Convert to `https://api.yourdomain.com`

**Steps:**
1. Add DNS A Record: `api.yourdomain.com` → `18.197.254.230`
2. Install Let's Encrypt on Lightsail:
   ```bash
   sudo apt install -y certbot python3-certbot-apache
   sudo certbot --apache -d api.yourdomain.com
   ```
3. Update Django settings to use HTTPS
4. Update frontend API calls to use HTTPS URLs

**Cost:** $0 (using existing domain + free Let's Encrypt certificate)

### 2. 🔐 Private Repository Deployment Fix
**Current Issue:** Deployment only works with public repository

**Solution Options:**
- **Option A:** Use GitHub Personal Access Token in secrets
- **Option B:** Use SSH Deploy Keys (already added but not working with GitHub Actions)
- **Option C:** Use GitHub App authentication

**Recommended Fix:** Update `.github/workflows/deploy.yml` to use Personal Access Token:
```yaml
# Replace git clone line with:
sudo -u bitnami git clone https://${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }}.git django_project
```

### 3. 🐍 Production Server Setup
**Current:** Using Django development server (not production-ready)
**Goal:** Setup proper production server

**Options:**
- **Option A:** Fix Apache + WSGI configuration (Python path issue)
- **Option B:** Setup Nginx + Gunicorn
- **Option C:** Use Docker with proper WSGI server

**Apache WSGI Fix Needed:**
- Fix Python path in `/opt/bitnami/apache2/conf/bitnami/bitnami-apps-prefix.conf`
- Ensure WSGI module loads Django properly

### 4. 🔧 Environment Variables
**Setup `.env` file properly for production:**
```bash
SECRET_KEY=your-secure-secret-key
DEBUG=False
ALLOWED_HOSTS=api.yourdomain.com,yourdomain.com
DATABASE_URL=your-database-url
```

### 5. 🗄️ Database Migration to Production DB
**Current:** SQLite (not production-ready for scale)
**Recommended:** PostgreSQL or MySQL

**Steps:**
1. Setup AWS RDS instance
2. Update Django DATABASE settings
3. Migrate data from SQLite to production DB

### 6. 📝 Static Files Serving
**Current Issue:** Static files may not serve properly in production
**Fix:** Configure Apache/Nginx to serve static files directly

### 7. 📊 Monitoring & Logging
**Setup:**
- Error logging
- Performance monitoring
- Health check endpoints
- Log rotation

### 8. 🛡️ Security Hardening
**Tasks:**
- Change Django SECRET_KEY
- Set DEBUG=False for production
- Setup proper CORS settings (remove CORS_ALLOW_ALL_ORIGINS=True)
- Add security headers
- Setup firewall rules (close unnecessary ports)

## 🚨 Current Known Issues

1. **Apache WSGI Error:** 
   - Error: `ModuleNotFoundError: No module named 'project_mutanda_django'`
   - Workaround: Using Django dev server on port 8080
   - Fix needed: Correct Python path in Apache configuration

2. **Public Repository Requirement:**
   - GitHub Actions only works with public repo
   - Private repo deployment fails with SSH authentication

3. **Development Server in Production:**
   - Currently using `python manage.py runserver` 
   - Not suitable for production traffic
   - Need proper WSGI server

## 📱 Frontend Integration Ready
Your API is ready for frontend use:

**Base URL:** `http://18.197.254.230:8080`
**After SSL:** `https://api.yourdomain.com`

**Example Frontend Code:**
```javascript
const API_BASE = 'http://18.197.254.230:8080';

// Authentication
const login = async (username, password) => {
  const response = await fetch(`${API_BASE}/api/token/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  return response.json();
};

// API Calls with Auth
const fetchData = async (token) => {
  const response = await fetch(`${API_BASE}/api/medicine/`, {
    headers: { 
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return response.json();
};
```

## 🎯 Quick Wins (Easy to implement)

1. **SSL Certificate:** ~30 minutes, $0 cost
2. **Private Repo Fix:** ~15 minutes, change one line in workflow
3. **Environment Variables:** ~10 minutes, better security
4. **Static Files:** ~20 minutes, proper asset serving

## 📞 Need Help?
- All deployment automation is working
- Django API is functional and ready for frontend
- These are optimization tasks for production readiness
- Current setup is perfect for development and testing

---
*Generated on: August 29, 2025*
*Django Version: 5.2.5*
*Deployment: AWS Lightsail + GitHub Actions*