# Production Deployment Guide - e-flow Monitor

## 🎯 Goal: 24/7 Reliable Data Collection

This guide ensures your e-flow monitor runs continuously without interruption.

---

## ✅ Enhanced Features

### Reliability Features Now Active:
- ✅ **Automatic Retry**: 3 attempts per data collection with 5s delays
- ✅ **Auto-Restart**: Restarts automatically on crashes (up to 5 times)
- ✅ **Health Monitoring**: Status checks every 5 minutes
- ✅ **Error Tracking**: Monitors consecutive failures (max 10 before alert)
- ✅ **Graceful Shutdown**: Clean exit on Ctrl+C or system signals
- ✅ **Comprehensive Logging**: All events logged to monitor.log

---

## 🚀 Deployment Options

### Option 1: Simple Python Process (Development/Testing)

**Start the monitor:**
```bash
python monitor.py
```

**Features:**
- Automatic retry on failures (3 attempts)
- Auto-restart on crashes (5 times max)
- Health checks every 5 minutes
- Logs to console + monitor.log

**Keep running in background:**
```bash
# Using nohup
nohup python monitor.py > monitor_output.log 2>&1 &

# Or using screen
screen -S e-flow
python monitor.py
# Press Ctrl+A then D to detach
```

---

### Option 2: Systemd Service (Production Linux)

**Best for:** Ubuntu/Debian/CentOS servers running 24/7

**Setup:**
```bash
# 1. Copy application to /opt
sudo mkdir -p /opt/e-flow
sudo cp -r . /opt/e-flow/
cd /opt/e-flow

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. Install systemd service
sudo cp e-flow-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload

# 4. Enable and start service
sudo systemctl enable e-flow-monitor
sudo systemctl start e-flow-monitor

# 5. Check status
sudo systemctl status e-flow-monitor
```

**Service Features:**
- ✅ Starts automatically on boot
- ✅ Restarts automatically on failure (every 30s)
- ✅ Rate limiting (max 10 restarts in 5 minutes)
- ✅ Resource limits (512MB RAM, 50% CPU)
- ✅ Security hardening enabled
- ✅ Integrated with system logging

**Monitoring commands:**
```bash
# View live logs
sudo journalctl -u e-flow-monitor -f

# View recent logs
sudo journalctl -u e-flow-monitor -n 100

# Restart service
sudo systemctl restart e-flow-monitor

# Stop service
sudo systemctl stop e-flow-monitor

# Check if running
sudo systemctl is-active e-flow-monitor
```

---

### Option 3: Docker Container (Cross-Platform)

**Best for:** Any system with Docker, easy deployment, portability

**Setup:**
```bash
# 1. Build and start
docker-compose up -d

# 2. Check status
docker-compose ps

# 3. View logs
docker-compose logs -f monitor

# 4. Restart if needed
docker-compose restart monitor
```

**Docker Features:**
- ✅ Isolated environment
- ✅ Automatic restart (restart: unless-stopped)
- ✅ Health checks every 5 minutes
- ✅ Resource limits (512MB RAM, 50% CPU)
- ✅ Log rotation (10MB per file, 3 files max)
- ✅ Runs both monitor + dashboard

**Docker Management:**
```bash
# Stop all services
docker-compose down

# View monitor logs
docker logs -f e-flow-monitor

# Check health status
docker inspect e-flow-monitor | grep Health -A 10

# Rebuild after code changes
docker-compose up -d --build

# Clean restart
docker-compose down && docker-compose up -d
```

---

## 📊 Monitoring & Health Checks

### Check Monitor Status

**Method 1: Check logs**
```bash
# Last 50 lines
tail -n 50 monitor.log

# Live monitoring
tail -f monitor.log

# Search for errors
grep "ERROR\|CRITICAL" monitor.log

# Search for health checks
grep "HEALTH CHECK" monitor.log
```

**Method 2: Check database**
```bash
# Count total measurements
sqlite3 flow_data.db "SELECT COUNT(*) FROM measurements;"

# Show last 10 measurements
sqlite3 flow_data.db "SELECT * FROM measurements ORDER BY timestamp DESC LIMIT 10;"

# Check most recent timestamp
sqlite3 flow_data.db "SELECT MAX(timestamp) FROM measurements;"
```

**Method 3: Check process**
```bash
# Is it running?
ps aux | grep monitor.py

# For systemd
sudo systemctl status e-flow-monitor

# For Docker
docker ps | grep e-flow-monitor
```

### Health Check Indicators

**🟢 HEALTHY:**
- Consecutive errors: 0-2
- Last success: < 5 minutes ago
- Success rate: > 80%
- Health status: "HEALTHY"

**🟡 WARNING:**
- Consecutive errors: 3-5
- Last success: 5-10 minutes ago
- Success rate: 50-80%

**🔴 UNHEALTHY:**
- Consecutive errors: > 10
- Last success: > 10 minutes ago
- Success rate: < 50%
- Health status: "UNHEALTHY"

---

## 🔧 Troubleshooting

### Monitor Not Starting

**Check 1: Dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**Check 2: Permissions**
```bash
# Ensure database is writable
chmod 644 flow_data.db

# Ensure log file is writable
touch monitor.log
chmod 644 monitor.log
```

**Check 3: Configuration**
```bash
# Verify config
python -c "from config import MONITOR_ENABLED, MONITOR_URL; print(f'Enabled: {MONITOR_ENABLED}, URL: {MONITOR_URL[:50]}')"
```

### Monitor Keeps Failing

**Check logs for errors:**
```bash
tail -n 100 monitor.log | grep -i error
```

**Common issues:**

1. **Network connection failed**
   - Check internet connectivity
   - Verify MONITOR_URL is accessible
   - Check firewall settings

2. **Playwright/Chromium issues**
   - Reinstall: `playwright install chromium --with-deps`
   - Check system resources (RAM, CPU)

3. **Database locked**
   - Close other connections to flow_data.db
   - Restart the monitor

4. **CSS selectors not working**
   - Website structure may have changed
   - Update selectors in config.py

### High Error Rate

**Investigate:**
```bash
# Count errors in last hour
grep "ERROR" monitor.log | grep "$(date +%Y-%m-%d)" | wc -l

# Show unique error messages
grep "ERROR" monitor.log | awk -F'ERROR - ' '{print $2}' | sort | uniq -c
```

**Solutions:**
- Increase RETRY_DELAY in monitor.py
- Increase MAX_RETRY_ATTEMPTS
- Check if website is down or changed
- Verify system resources (disk space, RAM)

---

## 📈 Performance Optimization

### Reduce Resource Usage

**Option 1: Increase interval**
```python
# In config.py
MONITOR_INTERVAL = 120  # Check every 2 minutes instead of 1
```

**Option 2: Adjust retry settings**
```python
# In monitor.py
MAX_RETRY_ATTEMPTS = 2  # Reduce from 3 to 2
RETRY_DELAY = 3  # Reduce from 5 to 3 seconds
```

### Monitor Multiple Devices

Add more devices to `config.py`:
```python
DEVICES = {
    "FIT100": {
        "name": "FIT100 Main Inflow Lismore STP",
        "location": "Lismore STP",
        "selectors": {...}
    },
    "FIT200": {
        "name": "FIT200 Secondary Flow",
        "location": "Secondary Site",
        "selectors": {...}
    }
}
```

---

## 🔒 Security Best Practices

### 1. File Permissions
```bash
chmod 600 config.py  # Restrict config access
chmod 644 flow_data.db  # Database readable
chmod 644 monitor.log  # Logs readable
```

### 2. Run as Non-Root (Systemd)
```bash
# Service already configured to run as 'ubuntu' user
# Change in e-flow-monitor.service if needed:
# User=your-username
# Group=your-group
```

### 3. Firewall Configuration
```bash
# Only needed for dashboard access
sudo ufw allow 8501/tcp
```

---

## 📋 Maintenance Tasks

### Daily
- ✅ Check health status in logs
- ✅ Verify data is being collected

### Weekly
- ✅ Review error logs
- ✅ Check disk space
- ✅ Verify success rate > 90%

### Monthly
- ✅ Rotate log files if large
- ✅ Backup database
- ✅ Update dependencies

**Backup database:**
```bash
# Create backup
cp flow_data.db "flow_data_backup_$(date +%Y%m%d).db"

# Automated backup script
echo "0 3 * * * cp /opt/e-flow/flow_data.db /opt/e-flow/backups/flow_data_\$(date +\%Y\%m\%d).db" | crontab -
```

**Rotate logs:**
```bash
# If monitor.log > 100MB
mv monitor.log monitor.log.old
touch monitor.log
sudo systemctl restart e-flow-monitor  # If using systemd
```

---

## 🎯 Success Metrics

Your monitor is running optimally when:

- ✅ **Uptime**: > 99.9% (< 10 minutes downtime per week)
- ✅ **Success Rate**: > 90% (check health logs)
- ✅ **Consecutive Errors**: < 3
- ✅ **Data Freshness**: Latest measurement < 2 minutes old
- ✅ **Resource Usage**: < 256MB RAM, < 25% CPU
- ✅ **Log Growth**: < 10MB per day

---

## 🆘 Emergency Recovery

### Complete System Failure

```bash
# 1. Stop everything
sudo systemctl stop e-flow-monitor  # or docker-compose down

# 2. Backup current state
cp flow_data.db flow_data_emergency_backup.db
cp monitor.log monitor_emergency.log

# 3. Fresh start
rm monitor.log
touch monitor.log

# 4. Verify configuration
python -c "from config import *; print('Config OK')"

# 5. Test single run
python -c "from monitor import ContinuousMonitor; import asyncio; m = ContinuousMonitor(); asyncio.run(m.check_for_updates())"

# 6. Restart service
sudo systemctl start e-flow-monitor  # or docker-compose up -d
```

---

## 📞 Support Checklist

When reporting issues, include:

1. **System Info:**
   - OS and version
   - Python version
   - Deployment method (systemd/docker/manual)

2. **Logs:**
   ```bash
   # Last 100 lines
   tail -n 100 monitor.log
   
   # Or for systemd
   sudo journalctl -u e-flow-monitor -n 100
   ```

3. **Status:**
   - Last successful data collection time
   - Current consecutive error count
   - Success rate from health check

4. **Database:**
   ```bash
   # Recent measurements count
   sqlite3 flow_data.db "SELECT COUNT(*) FROM measurements WHERE timestamp > datetime('now', '-1 hour');"
   ```

---

## ✅ Final Checklist

Before going to production:

- [ ] Monitor runs successfully for 24 hours
- [ ] Health checks show "HEALTHY" status
- [ ] Success rate > 90%
- [ ] Logs show no critical errors
- [ ] Database growing with new measurements
- [ ] Auto-restart tested (kill process, verify restart)
- [ ] Backup strategy in place
- [ ] Monitoring/alerting configured
- [ ] Documentation reviewed

---

**Your e-flow monitor is now production-ready and bulletproof! 🎉**
