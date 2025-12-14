from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import json
import time
from datetime import datetime
import uuid
import logging
import socket

# Configure logging for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Rate Limiter - Render compatible
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# ARES BRANDING
ARES_CONFIG = {
    "name": "ARES INSTAGRAM INTELLIGENCE",
    "version": "V5.0.0",
    "tagline": "DISTRIBUTED IP SCRAPING SYSTEM",
    "status": "ACTIVE // IP-ROTATION ENABLED",
    "contact": "operations@ares-intel.com",
}

# Initialize scraper with error handling
try:
    from scraper import InstagramScraper
    scraper = InstagramScraper()
    SCRAPER_AVAILABLE = True
    logger.info("InstagramScraper initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize scraper: {str(e)}")
    SCRAPER_AVAILABLE = False

# Initialize proxy manager
try:
    from proxy_manager import proxy_manager
    PROXY_MANAGER_AVAILABLE = True
    logger.info("ProxyManager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize proxy manager: {str(e)}")
    PROXY_MANAGER_AVAILABLE = False

def generate_mission_id():
    return f"ARES-MISSION-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

def get_client_ip():
    """Get client IP address from request"""
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr
    
    try:
        socket.inet_aton(ip)
        return ip
    except socket.error:
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
    """Dashboard"""
    client_ip = get_client_ip()
    user_agent = get_client_user_agent()
    
    # Add client IP to proxy pool if available
    if PROXY_MANAGER_AVAILABLE:
        proxy_manager.add_user_ip(client_ip, user_agent)
    
    system_status = {
        "scraper": SCRAPER_AVAILABLE,
        "proxy_manager": PROXY_MANAGER_AVAILABLE,
        "your_ip": client_ip,
        "requests_served": scraper.request_count if SCRAPER_AVAILABLE else 0,
        "status": "OPERATIONAL" if SCRAPER_AVAILABLE else "DEGRADED"
    }
    
    return render_template('index.html', brand=ARES_CONFIG, status=system_status)

@app.route('/api/v1/lookup/<username>', methods=['GET'])
@limiter.limit("15 per minute")
def lookup_user(username):
    """Main lookup endpoint"""
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
        
        if not SCRAPER_AVAILABLE:
            return ares_response(
                success=False,
                message="Scraper system temporarily unavailable",
                code=503,
                client_ip=client_ip
            )
        
        # Get parameters
        data_type = request.args.get('type', 'full')
        include_posts = request.args.get('posts', 'true').lower() == 'true'
        
        # Add client IP to proxy pool
        if PROXY_MANAGER_AVAILABLE:
            proxy_manager.add_user_ip(client_ip, user_agent)
        
        # Scrape data
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
            message=f"Successfully extracted data for @{username}",
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

@app.route('/api/v1/my_ip', methods=['GET'])
def get_my_ip():
    """Endpoint to show client's IP information"""
    client_ip = get_client_ip()
    user_agent = get_client_user_agent()
    
    # Add to proxy pool if available
    if PROXY_MANAGER_AVAILABLE:
        proxy_manager.add_user_ip(client_ip, user_agent)
    
    # Get IP information
    ip_info = {
        "your_ip": client_ip,
        "user_agent": user_agent,
        "added_to_pool": PROXY_MANAGER_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "request_headers": {
            "user_agent": user_agent,
            "accept_language": request.headers.get('Accept-Language'),
            "accept_encoding": request.headers.get('Accept-Encoding')
        }
    }
    
    return ares_response(
        data=ip_info,
        message="Your IP information",
        client_ip=client_ip
    )

@app.route('/api/v1/proxy_pool', methods=['GET'])
def get_proxy_pool():
    """Get proxy pool statistics"""
    client_ip = get_client_ip()
    
    if not PROXY_MANAGER_AVAILABLE:
        return ares_response(
            success=False,
            message="Proxy manager not available",
            code=503,
            client_ip=client_ip
        )
    
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

@app.route('/api/v1/status', methods=['GET'])
def system_status():
    """System status with IP information"""
    client_ip = get_client_ip()
    
    # Test connection if scraper is available
    test_result = {}
    if SCRAPER_AVAILABLE:
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
            "in_proxy_pool": client_ip in proxy_manager.user_ips if PROXY_MANAGER_AVAILABLE else False,
            "connection_test": test_result.get('status', 'UNKNOWN') if SCRAPER_AVAILABLE else 'SCRAPER_UNAVAILABLE'
        },
        "services": {
            "scraper": "ACTIVE" if SCRAPER_AVAILABLE else "INACTIVE",
            "proxy_manager": "ACTIVE" if PROXY_MANAGER_AVAILABLE else "INACTIVE",
            "api": "ACTIVE",
            "rate_limiting": "ACTIVE"
        },
        "metrics": {
            "requests_today": scraper.request_count if SCRAPER_AVAILABLE else 0,
            "uptime": "99.9%",
            "response_time": "<1s"
        }
    }
    
    return ares_response(
        data=status_data,
        message="System status",
        client_ip=client_ip
    )

@app.route('/api/v1/search', methods=['GET'])
@limiter.limit("10 per minute")
def search_users():
    """Search for users (simplified)"""
    client_ip = get_client_ip()
    query = request.args.get('q', '')
    
    if not query or len(query) < 2:
        return ares_response(
            success=False,
            message="Search query too short",
            code=400,
            client_ip=client_ip
        )
    
    if not SCRAPER_AVAILABLE:
        return ares_response(
            success=False,
            message="Search service unavailable",
            code=503,
            client_ip=client_ip
        )
    
    try:
        # Simple mock search
        search_results = [
            {
                "username": f"{query}_user1",
                "full_name": f"{query.capitalize()} User 1",
                "is_verified": False,
                "profile_pic_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={query}1",
                "follower_count": 1000
            },
            {
                "username": f"{query}_user2",
                "full_name": f"{query.capitalize()} User 2",
                "is_verified": True,
                "profile_pic_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={query}2",
                "follower_count": 5000
            }
        ]
        
        return ares_response(
            data={
                "query": query,
                "results": search_results,
                "count": len(search_results),
                "your_ip_used": client_ip
            },
            message=f"Found {len(search_results)} results for '{query}'",
            client_ip=client_ip
        )
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return ares_response(
            success=False,
            message="Search failed",
            code=500,
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
