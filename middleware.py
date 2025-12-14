from flask import request, jsonify
import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.requests = {}
    
    def is_rate_limited(self, ip, limit=100, window=3600):
        current_time = time.time()
        
        if ip not in self.requests:
            self.requests[ip] = []
        
        # Remove old requests
        self.requests[ip] = [t for t in self.requests[ip] if current_time - t < window]
        
        # Check if limit exceeded
        if len(self.requests[ip]) >= limit:
            return True
        
        # Add current request
        self.requests[ip].append(current_time)
        return False

rate_limiter = RateLimiter()

def rate_limit(limit=100, window=3600):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr
            if rate_limiter.is_rate_limited(ip, limit, window):
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Try again in {window//60} minutes"
                }), 429
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        try:
            response = f(*args, **kwargs)
            duration = time.time() - start_time
            
            logger.info(
                f"{request.method} {request.path} - "
                f"{response[1] if isinstance(response, tuple) else 200} - "
                f"{duration:.3f}s"
            )
            
            return response
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"{request.method} {request.path} - ERROR: {str(e)} - {duration:.3f}s")
            raise
    
    return decorated_function
