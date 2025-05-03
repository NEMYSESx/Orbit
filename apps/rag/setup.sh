#!/bin/bash
# Setup script for Nginx with FastAPI, HTTPS, and connection pooling

# 1. Install Nginx if not already installed
sudo apt update
sudo apt install -y nginx

# 2. Create directory for SSL certificates
sudo mkdir -p /etc/nginx/ssl

# 3. Generate self-signed SSL certificate (valid for 365 days)
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/nginx.key \
  -out /etc/nginx/ssl/nginx.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=34.93.41.9"

# 4. Create Nginx configuration file
cat << 'EOF' | sudo tee /etc/nginx/sites-available/fastapi-app
upstream fastapi_backend {
    # Connection pooling configuration
    server 127.0.0.1:8000;  # Assuming FastAPI runs on port 8000
    keepalive 32;  # Keep up to 32 connections open
}

server {
    listen 80;
    server_name 34.93.41.9;
    
    # Redirect all HTTP traffic to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name 34.93.41.9;
    
    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/nginx.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    
    # Proxy settings for FastAPI
    location / {
        proxy_pass http://fastapi_backend;
        proxy_http_version 1.1;  # Required for keepalive connections
        proxy_set_header Connection "";  # Remove Connection header to enable keepalive
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 90s;
        proxy_send_timeout 90s;
        proxy_read_timeout 90s;
        
        # Buffer settings
        proxy_buffer_size 4k;
        proxy_buffers 8 16k;
        proxy_busy_buffers_size 32k;
    }
}
EOF

# 5. Enable the site by creating a symbolic link
sudo ln -sf /etc/nginx/sites-available/fastapi-app /etc/nginx/sites-enabled/

# 6. Test Nginx configuration
sudo nginx -t

# 7. Restart Nginx to apply changes
sudo systemctl restart nginx

echo "Nginx has been configured with HTTPS and connection pooling for FastAPI at 34.93.41.9"
echo "Make sure your FastAPI app is running on port 8000"