from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import json
import time
from datetime import datetime
import uuid
from functools import wraps
import logging
import socket

from scraper import InstagramScraper
from proxy_manager import proxy_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Rate Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# ARES BRANDING
ARES_CONFIG = {
    "name": "ARES INSTAGRAM INTELLIGENCE",
    "version": "V5.0.0",
    "tagline": "DISTRIBUTED IP SCARPING SYSTEM",
    "status": "ACTIVE // IP-ROTATION ENABLED",
    "contact": "operations@ares-intel.com",
}

# Initialize scraper
scraper = InstagramScraper()
SCRAPER_AVAILABLE = True

def generate_mission_id():
    return f"ARES-MISSION-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

def get_client_ip():
    """Get client IP address from request"""
    # Check for forwarded headers first (from proxies/load balancers)
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr
    
    # Validate IP address
    try:
        socket.inet_aton(ip)
        return ip
    except socket.error:
        # Fallback to remote_addr if IP is invalid
        return request.remote_addr

def get_client_user_agent():
    """Get client user agent"""
    return request.headers.get('User-Agent', 'Unknown')

def ares_response(data=None, success=True, message="", code=200, client_ip=None):
    """Standardized Ares API response"""
    response = {
        "meta": {
            "success": success,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mission_id": generate_mission_id(),
            "version": ARES_CONFIG["version"],
            "platform": ARES_CONFIG["name"],
            "client_ip_used": client_ip or "system_ip"
        }
    }
    
    if message:
        response["meta"]["message"] = message
    
    if data is not None:
        response["data"] = data
    
    if not success:
        response["meta"]["code"] = f"ARES-{code}"
    
    return jsonify(response), code

@app.route('/')
def home():
    """Dashboard with IP information"""
    client_ip = get_client_ip()
    user_agent = get_client_user_agent()
    
    # Add client IP to proxy pool
    proxy_manager.add_user_ip(client_ip, user_agent)
    
    system_status = {
        "scraper": SCRAPER_AVAILABLE,
        "your_ip": client_ip,
        "ip_added_to_pool": True,
        "proxy_pool_stats": proxy_manager.get_stats(),
        "requests_served": scraper.request_count
    }
    return render_template('index.html', brand=ARES_CONFIG, status=system_status)

@app.route('/api/v1/lookup/<username>', methods=['GET'])
@limiter.limit("15 per minute")
def lookup_user(username):
    """Main lookup endpoint using client's IP"""
    start_time = time.time()
    
    try:
        # Get client IP and user agent
        client_ip = get_client_ip()
        user_agent = get_client_user_agent()
        
        logger.info(f"Lookup request from IP: {client_ip} for username: {username}")
        
        # Validate username
        if not username or len(username) < 1 or len(username) > 30:
            return ares_response(
                success=False,
                message="Invalid username format",
                code=400,
                client_ip=client_ip
            )
        
        # Get parameters
        data_type = request.args.get('type', 'full')
        include_posts = request.args.get('posts', 'true').lower() == 'true'
        
        # Scrape using client's IP
        scraped_data = scraper.scrape_profile(username, client_ip, user_agent)
        
        if 'error' in scraped_data:
            error_msg = scraped_data.get('error', 'Unknown error')
            if 'private' in error_msg.lower():
                return ares_response(
                    success=False,
                    message="Profile is private",
                    code=403,
                    data={
                        "username": username, 
                        "private": True,
                        "your_ip_used": client_ip
                    },
                    client_ip=client_ip
                )
            elif 'not found' in error_msg.lower():
                return ares_response(
                    success=False,
                    message="Profile not found",
                    code=404,
                    data={
                        "username": username,
                        "your_ip_used": client_ip
                    },
                    client_ip=client_ip
                )
            else:
                return ares_response(
                    success=False,
                    message=f"Extraction failed: {error_msg}",
                    code=500,
                    client_ip=client_ip
                )
        
        # Format response
        response_data = {
            "target": {
                "username": username,
                "url": f"https://instagram.com/{username}",
                "extracted_at": datetime.utcnow().isoformat() + "Z"
            },
            "profile": scraped_data.get('profile', {}),
            "extraction_info": {
                "your_ip_used": client_ip,
                "extraction_method": scraped_data.get('used_ip', 'direct'),
                "extraction_time_ms": scraped_data.get('extraction_time', 0),
                "data_points": scraped_data.get('data_points', 0),
                "cached": scraped_data.get('cached', False)
            }
        }
        
        if include_posts and 'posts' in scraped_data:
            response_data["posts"] = scraped_data['posts']
        
        total_time = int((time.time() - start_time) * 1000)
        response_data["extraction_info"]["total_time_ms"] = total_time
        
        return ares_response(
            data=response_data,
            message=f"Successfully extracted data for @{username} using your IP",
            client_ip=client_ip
        )
        
    except Exception as e:
        logger.error(f"Lookup error: {str(e)}")
        client_ip = get_client_ip()
        return ares_response(
            success=False,
            message=f"Internal server error: {str(e)}",
            code=500,
            client_ip=client_ip
        )

@app.route('/api/v1/lookup_direct/<username>', methods=['GET'])
@limiter.limit("10 per minute")
def lookup_user_direct(username):
    """Lookup using only client's direct IP (no proxy fallback)"""
    try:
        client_ip = get_client_ip()
        user_agent = get_client_user_agent()
        
        logger.info(f"Direct lookup from IP: {client_ip} for username: {username}")
        
        # Scrape using ONLY client's IP
        url = f"https://www.instagram.com/{username}/"
        headers = {'User-Agent': user_agent}
        
        # Simulate direct request from client's IP
        # In production, you would need proper IP forwarding
        response = scraper._make_request_with_proxy(url, client_ip, user_agent)
        
        if response and response.status_code == 200:
            # Process the response
            scraped_data = scraper._parse_html_directly(response.text, username)
            
            return ares_response(
                data={
                    "profile": scraped_data.get('profile', {}),
                    "extraction_info": {
                        "method": "direct_client_ip",
                        "your_ip": client_ip,
                        "success": True
                    }
                },
                message=f"Direct extraction using your IP completed",
                client_ip=client_ip
            )
        else:
            return ares_response(
                success=False,
                message="Direct extraction failed",
                code=500,
                client_ip=client_ip
            )
        
    except Exception as e:
        client_ip = get_client_ip()
        return ares_response(
            success=False,
            message=f"Direct extraction error: {str(e)}",
            code=500,
            client_ip=client_ip
        )

@app.route('/api/v1/my_ip', methods=['GET'])
def get_my_ip():
    """Endpoint to show client's IP information"""
    client_ip = get_client_ip()
    user_agent = get_client_user_agent()
    
    # Add to proxy pool
    proxy_manager.add_user_ip(client_ip, user_agent)
    
    # Get IP information
    ip_info = {
        "your_ip": client_ip,
        "user_agent": user_agent,
        "added_to_pool": True,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "headers": dict(request.headers)
    }
    
    # Try to get geolocation (simplified)
    try:
        import geoip2.database
        # This would require geoip2 database
        ip_info["location"] = "Unknown (Install geoip2 for location)"
    except:
        ip_info["location"] = "Geolocation not available"
    
    return ares_response(
        data=ip_info,
        message="Your IP information",
        client_ip=client_ip
    )

@app.route('/api/v1/proxy_pool', methods=['GET'])
def get_proxy_pool():
    """Get proxy pool statistics"""
    client_ip = get_client_ip()
    stats = proxy_manager.get_stats()
    
    return ares_response(
        data={
            "proxy_pool": stats,
            "your_ip_in_pool": client_ip in proxy_manager.user_ips,
            "total_user_ips": len(proxy_manager.user_ips),
            "your_ip": client_ip
        },
        message="Proxy pool statistics",
        client_ip=client_ip
    )

@app.route('/api/v1/batch', methods=['POST'])
@limiter.limit("5 per hour")
def batch_lookup():
    """Batch process using client's IP"""
    try:
        client_ip = get_client_ip()
        user_agent = get_client_user_agent()
        
        data = request.get_json()
        if not data or 'usernames' not in data:
            return ares_response(
                success=False,
                message="No usernames provided",
                code=400,
                client_ip=client_ip
            )
        
        usernames = data['usernames']
        if not isinstance(usernames, list):
            return ares_response(
                success=False,
                message="Usernames must be a list",
                code=400,
                client_ip=client_ip
            )
        
        if len(usernames) > 5:
            return ares_response(
                success=False,
                message="Maximum 5 usernames per batch",
                code=400,
                client_ip=client_ip
            )
        
        results = []
        failed = []
        
        for username in usernames:
            try:
                scraped_data = scraper.scrape_profile(username, client_ip, user_agent)
                if 'error' not in scraped_data:
                    results.append({
                        "username": username,
                        "success": True,
                        "data": scraped_data.get('profile', {}),
                        "used_your_ip": True
                    })
                else:
                    failed.append({
                        "username": username,
                        "error": scraped_data.get('error')
                    })
            except Exception as e:
                failed.append({
                    "username": username,
                    "error": str(e)
                })
        
        return ares_response(
            data={
                "processed": len(usernames),
                "successful": len(results),
                "failed": len(failed),
                "your_ip_used": client_ip,
                "results": results,
                "failed_usernames": failed
            },
            message=f"Batch processing complete using your IP",
            client_ip=client_ip
        )
        
    except Exception as e:
        client_ip = get_client_ip()
        return ares_response(
            success=False,
            message=f"Batch processing failed: {str(e)}",
            code=500,
            client_ip=client_ip
        )

@app.route('/api/v1/status', methods=['GET'])
def system_status():
    """System status with IP information"""
    client_ip = get_client_ip()
    
    # Test connection with client's IP
    test_result = scraper.test_connection(client_ip)
    
    status_data = {
        "system": {
            "name": ARES_CONFIG["name"],
            "version": ARES_CONFIG["version"],
            "status": "OPERATIONAL",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "environment": os.environ.get('FLASK_ENV', 'production')
        },
        "your_ip": {
            "address": client_ip,
            "in_proxy_pool": client_ip in proxy_manager.user_ips,
            "connection_test": test_result.get('status', 'UNKNOWN'),
            "used_for_scraping": test_result.get('used_ip', 'direct')
        },
        "scraper": {
            "status": test_result.get('status', 'UNKNOWN'),
            "requests_today": scraper.request_count,
            "proxy_pool_stats": proxy_manager.get_stats()
        },
        "api": {
            "rate_limit": "200/day, 50/hour",
            "ip_rotation": "ENABLED",
            "your_ip_rotation": "ACTIVE"
        }
    }
    
    return ares_response(
        data=status_data,
        message="System status with IP information",
        client_ip=client_ip
    )

@app.route('/api/v1/refresh_proxies', methods=['POST'])
@limiter.limit("2 per hour")
def refresh_proxies():
    """Refresh proxy pool (admin endpoint)"""
    client_ip = get_client_ip()
    
    # Simple auth check
    auth_key = request.headers.get('X-API-Key')
    if auth_key != os.environ.get('ADMIN_KEY', 'ares-admin-2024'):
        return ares_response(
            success=False,
            message="Unauthorized",
            code=401,
            client_ip=client_ip
        )
    
    added = proxy_manager.refresh_proxy_pool()
    
    return ares_response(
        data={
            "proxies_added": added,
            "total_proxies": len(proxy_manager.proxies),
            "user_ips": len(proxy_manager.user_ips)
        },
        message="Proxy pool refreshed",
        client_ip=client_ip
    )

@app.errorhandler(404)
def not_found(e):
    client_ip = get_client_ip()
    return ares_response(
        success=False,
        message="Endpoint not found",
        code=404,
        client_ip=client_ip
    )

@app.errorhandler(429)
def rate_limit_exceeded(e):
    client_ip = get_client_ip()
    return ares_response(
        success=False,
        message="Rate limit exceeded. Please try again later.",
        code=429,
        client_ip=client_ip
    )

@app.errorhandler(500)
def internal_error(e):
    client_ip = get_client_ip()
    logger.error(f"500 error: {str(e)}")
    return ares_response(
        success=False,
        message="Internal server error",
        code=500,
        client_ip=client_ip
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
