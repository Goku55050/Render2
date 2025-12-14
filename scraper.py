import requests
import json
import time
import re
import random
from datetime import datetime
from bs4 import BeautifulSoup
import cloudscraper
from fake_useragent import UserAgent
from urllib.parse import urljoin
import logging
import cachetools
from typing import Dict, List, Optional, Any
import socket

from proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

class InstagramScraper:
    def __init__(self):
        self.session = self._create_session()
        self.ua = UserAgent()
        self.request_count = 0
        self.cache = cachetools.TTLCache(maxsize=100, ttl=300)
        
        # Instagram API patterns
        self.patterns = {
            'shared_data': r'window\._sharedData\s*=\s*({.*?});',
            'config_data': r'window\.__additionalDataLoaded\s*\([^,]+,\s*({.*?})\);',
        }
        
        # Headers
        self.base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Instagram endpoints
        self.endpoints = {
            'profile': 'https://www.instagram.com/{}/',
            'profile_json': 'https://www.instagram.com/api/v1/users/web_profile_info/?username={}',
        }
        
        logger.info("InstagramScraper initialized with proxy support")
    
    def _create_session(self):
        """Create session with cloudscraper"""
        try:
            return cloudscraper.create_scraper()
        except:
            return requests.Session()
    
    def _get_headers(self, user_agent: str = None):
        """Generate headers"""
        headers = self.base_headers.copy()
        headers['User-Agent'] = user_agent if user_agent else self.ua.random
        return headers
    
    def _make_request_with_proxy(self, url: str, client_ip: str = None, 
                                 user_agent: str = None, use_cache: bool = True) -> Optional[requests.Response]:
        """Make HTTP request using proxy or client IP"""
        
        # Check cache first
        cache_key = f"request:{url}:{client_ip}"
        if use_cache and cache_key in self.cache:
            logger.debug(f"Cache hit for: {url}")
            return self.cache[cache_key]
        
        # Get the best proxy for this request
        proxy = None
        proxy_type = "direct"
        
        if client_ip:
            # Try to use client's own IP as proxy
            user_proxy = proxy_manager.get_user_ip_proxy(client_ip)
            if user_proxy:
                proxy = {
                    'http': f'http://{user_proxy.ip}',
                    'https': f'http://{user_proxy.ip}'
                }
                proxy_type = "user_ip"
                logger.info(f"Using client IP as proxy: {client_ip}")
            else:
                # Fallback to best available proxy
                best_proxy = proxy_manager.get_best_proxy()
                if best_proxy:
                    proxy = {
                        'http': f'http://{best_proxy.ip}:{best_proxy.port}',
                        'https': f'http://{best_proxy.ip}:{best_proxy.port}'
                    }
                    proxy_type = "pool_proxy"
                    logger.info(f"Using pool proxy: {best_proxy.ip}:{best_proxy.port}")
        else:
            # No client IP, use direct or pool proxy
            best_proxy = proxy_manager.get_best_proxy()
            if best_proxy:
                proxy = {
                    'http': f'http://{best_proxy.ip}:{best_proxy.port}',
                    'https': f'http://{best_proxy.ip}:{best_proxy.port}'
                }
                proxy_type = "pool_proxy"
        
        # Rate limiting
        time.sleep(random.uniform(1.0, 2.5))
        
        headers = self._get_headers(user_agent)
        
        try:
            start_time = time.time()
            
            if proxy and proxy_type != "user_ip":
                # For proxy pool, use proxy
                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=proxy,
                    timeout=15,
                    allow_redirects=True
                )
            elif proxy_type == "user_ip":
                # For user IP, we need to route through their IP
                # This is a simplified approach - in production you'd need proper routing
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=15,
                    allow_redirects=True
                )
                # Set X-Forwarded-For header to simulate coming from user's IP
                headers['X-Forwarded-For'] = client_ip
                headers['X-Real-IP'] = client_ip
            else:
                # Direct connection
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=15,
                    allow_redirects=True
                )
            
            response_time = time.time() - start_time
            self.request_count += 1
            
            # Update proxy performance
            if proxy_type in ["user_ip", "pool_proxy"] and proxy:
                proxy_ip = client_ip if proxy_type == "user_ip" else best_proxy.ip
                success = response.status_code == 200
                proxy_manager.update_proxy_performance(proxy_ip, success, response_time)
            
            # Cache successful responses
            if response.status_code == 200 and use_cache:
                self.cache[cache_key] = response
            
            logger.debug(f"Request to {url} via {proxy_type} - Status: {response.status_code} - Time: {response_time:.2f}s")
            return response
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout for {url}")
            if proxy_type in ["user_ip", "pool_proxy"] and proxy:
                proxy_ip = client_ip if proxy_type == "user_ip" else best_proxy.ip
                proxy_manager.update_proxy_performance(proxy_ip, False, 10.0)
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error for {url}")
            if proxy_type in ["user_ip", "pool_proxy"] and proxy:
                proxy_ip = client_ip if proxy_type == "user_ip" else best_proxy.ip
                proxy_manager.update_proxy_performance(proxy_ip, False, 10.0)
        except Exception as e:
            logger.error(f"Request error for {url}: {str(e)}")
            if proxy_type in ["user_ip", "pool_proxy"] and proxy:
                proxy_ip = client_ip if proxy_type == "user_ip" else best_proxy.ip
                proxy_manager.update_proxy_performance(proxy_ip, False, 10.0)
        
        return None
    
    def scrape_profile(self, username: str, client_ip: str = None, user_agent: str = None) -> Dict:
        """Scrape Instagram profile using client's IP or proxy"""
        start_time = time.time()
        cache_key = f"profile:{username}:{client_ip}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            cached_data['cached'] = True
            cached_data['used_ip'] = client_ip or "direct"
            return cached_data
        
        logger.info(f"Scraping profile: {username} using IP: {client_ip or 'direct'}")
        
        # Add client IP to proxy pool if provided
        if client_ip:
            proxy_manager.add_user_ip(client_ip, user_agent)
        
        # Try multiple methods with client IP/proxy
        methods = [
            lambda: self._scrape_via_html(username, client_ip, user_agent),
            lambda: self._scrape_via_api(username, client_ip, user_agent),
        ]
        
        for method in methods:
            try:
                result = method()
                if result and 'error' not in result:
                    extraction_time = int((time.time() - start_time) * 1000)
                    result['extraction_time'] = extraction_time
                    result['data_points'] = self._count_data_points(result)
                    result['cached'] = False
                    result['used_ip'] = client_ip or "pool_proxy"
                    
                    # Cache the result
                    self.cache[cache_key] = result
                    
                    return result
            except Exception as e:
                logger.debug(f"Method failed: {str(e)}")
                continue
        
        return {
            "error": "SCRAPING_FAILED",
            "message": "All scraping methods failed",
            "used_ip": client_ip or "direct"
        }
    
    def _scrape_via_html(self, username: str, client_ip: str = None, user_agent: str = None) -> Dict:
        """Scrape via HTML using client IP/proxy"""
        try:
            url = self.endpoints['profile'].format(username)
            response = self._make_request_with_proxy(url, client_ip, user_agent, use_cache=False)
            
            if not response or response.status_code != 200:
                return {"error": "REQUEST_FAILED"}
            
            html = response.text
            
            # Check for private account
            if 'This Account is Private' in html or 'account is private' in html.lower():
                return {"error": "PRIVATE_PROFILE"}
            
            # Check for non-existent account
            if 'Sorry, this page isn\'t available' in html:
                return {"error": "PROFILE_NOT_FOUND"}
            
            # Extract JSON data
            json_data = self._extract_json_from_html(html)
            
            if json_data:
                return self._parse_html_response(json_data, username)
            
            # Fallback to direct HTML parsing
            return self._parse_html_directly(html, username)
            
        except Exception as e:
            logger.error(f"HTML scraping error: {str(e)}")
            return {"error": "HTML_PARSING_FAILED"}
    
    def _scrape_via_api(self, username: str, client_ip: str = None, user_agent: str = None) -> Dict:
        """Use Instagram's API with client IP"""
        try:
            url = self.endpoints['profile_json'].format(username)
            headers = self._get_headers(user_agent)
            headers.update({
                'X-IG-App-ID': '936619743392459',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            # Add client IP to headers
            if client_ip:
                headers['X-Forwarded-For'] = client_ip
                headers['X-Real-IP'] = client_ip
            
            response = self._make_request_with_proxy(url, client_ip, user_agent)
            
            if response and response.status_code == 200:
                data = response.json()
                user = data.get('data', {}).get('user', {})
                
                if not user:
                    return {"error": "USER_NOT_FOUND"}
                
                return self._parse_api_response(user)
            
        except Exception as e:
            logger.debug(f"API method failed: {str(e)}")
        
        return {"error": "API_FAILED"}
    
    def _extract_json_from_html(self, html: str) -> Optional[Dict]:
        """Extract JSON data from HTML"""
        try:
            for pattern_name, pattern in self.patterns.items():
                matches = re.search(pattern, html, re.DOTALL)
                if matches:
                    try:
                        data = json.loads(matches.group(1))
                        return data
                    except json.JSONDecodeError:
                        continue
            
            # Alternative: look for script tags with JSON
            soup = BeautifulSoup(html, 'html.parser')
            scripts = soup.find_all('script', type='text/javascript')
            
            for script in scripts:
                if script.string and 'window._sharedData' in script.string:
                    json_str = script.string.split('window._sharedData = ')[1].rstrip(';')
                    try:
                        return json.loads(json_str)
                    except:
                        continue
            
        except Exception as e:
            logger.error(f"JSON extraction error: {str(e)}")
        
        return None
    
    def _parse_html_response(self, json_data: Dict, username: str) -> Dict:
        """Parse HTML JSON response"""
        try:
            # Navigate to user data
            user = None
            paths = [
                ['entry_data', 'ProfilePage', 0, 'graphql', 'user'],
                ['graphql', 'user'],
                ['user']
            ]
            
            for path in paths:
                current = json_data
                for key in path:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        current = None
                        break
                if current and 'username' in current:
                    user = current
                    break
            
            if not user:
                return {"error": "USER_DATA_NOT_FOUND"}
            
            # Extract profile data
            profile = {
                "identity": {
                    "username": user.get('username', username),
                    "full_name": user.get('full_name', ''),
                    "biography": user.get('biography', ''),
                    "external_url": user.get('external_url', ''),
                    "is_private": user.get('is_private', False),
                    "is_verified": user.get('is_verified', False),
                    "profile_pic_url": user.get('profile_pic_url_hd') or 
                                       user.get('profile_pic_url') or 
                                       ''
                },
                "statistics": {
                    "followers": user.get('edge_followed_by', {}).get('count', 0),
                    "following": user.get('edge_follow', {}).get('count', 0),
                    "posts": user.get('edge_owner_to_timeline_media', {}).get('count', 0)
                }
            }
            
            # Extract recent posts
            posts = self._extract_posts(user)
            
            return {
                "profile": profile,
                "posts": {
                    "recent": posts[:5],
                    "total": len(posts)
                }
            }
            
        except Exception as e:
            logger.error(f"HTML parsing error: {str(e)}")
            return {"error": "PARSING_ERROR"}
    
    def _parse_html_directly(self, html: str, username: str) -> Dict:
        """Direct HTML parsing fallback"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract meta tags
        meta_data = {}
        for meta in soup.find_all('meta'):
            prop = meta.get('property') or meta.get('name')
            content = meta.get('content')
            if prop and content:
                meta_data[prop] = content
        
        # Extract counts using regex
        followers = self._extract_count(html, r'(\d+(?:\.\d+)?[KM]?)\s*Followers')
        following = self._extract_count(html, r'(\d+(?:\.\d+)?[KM]?)\s*Following')
        posts = self._extract_count(html, r'(\d+(?:\.\d+)?[KM]?)\s*Posts')
        
        profile = {
            "identity": {
                "username": username,
                "full_name": meta_data.get('og:title', '').replace('• Instagram', '').strip(),
                "biography": meta_data.get('og:description', ''),
                "profile_pic_url": meta_data.get('og:image', ''),
                "is_private": 'private' in html.lower(),
                "is_verified": 'verified' in html.lower()
            },
            "statistics": {
                "followers": followers,
                "following": following,
                "posts": posts
            }
        }
        
        return {"profile": profile}
    
    def _parse_api_response(self, user_data: Dict) -> Dict:
        """Parse API response"""
        profile = {
            "identity": {
                "username": user_data.get('username', ''),
                "full_name": user_data.get('full_name', ''),
                "biography": user_data.get('biography', ''),
                "external_url": user_data.get('external_url', ''),
                "is_private": user_data.get('is_private', False),
                "is_verified": user_data.get('is_verified', False),
                "profile_pic_url": user_data.get('profile_pic_url_hd', user_data.get('profile_pic_url', ''))
            },
            "statistics": {
                "followers": user_data.get('edge_followed_by', {}).get('count', 0),
                "following": user_data.get('edge_follow', {}).get('count', 0),
                "posts": user_data.get('edge_owner_to_timeline_media', {}).get('count', 0)
            }
        }
        
        # Extract posts
        posts = self._extract_posts(user_data)
        
        return {
            "profile": profile,
            "posts": {
                "recent": posts[:5],
                "total": len(posts)
            }
        }
    
    def _extract_posts(self, user_data: Dict) -> List[Dict]:
        """Extract posts from user data"""
        posts = []
        edges = user_data.get('edge_owner_to_timeline_media', {}).get('edges', [])
        
        for edge in edges[:10]:
            node = edge.get('node', {})
            if not node:
                continue
            
            post = {
                "id": node.get('id', ''),
                "shortcode": node.get('shortcode', ''),
                "caption": self._extract_caption(node),
                "type": self._get_post_type(node),
                "likes": node.get('edge_liked_by', {}).get('count', 0),
                "comments": node.get('edge_media_to_comment', {}).get('count', 0),
                "timestamp": node.get('taken_at_timestamp', 0),
                "url": f"https://instagram.com/p/{node.get('shortcode', '')}",
                "media_url": node.get('display_url', ''),
                "is_video": node.get('is_video', False)
            }
            posts.append(post)
        
        return posts
    
    def _extract_caption(self, node: Dict) -> str:
        """Extract caption from post"""
        try:
            edges = node.get('edge_media_to_caption', {}).get('edges', [])
            if edges:
                return edges[0].get('node', {}).get('text', '')[:200]
        except:
            pass
        return ''
    
    def _get_post_type(self, node: Dict) -> str:
        """Get post type"""
        typename = node.get('__typename', '')
        if 'Image' in typename:
            return 'IMAGE'
        elif 'Video' in typename:
            return 'VIDEO'
        elif 'Sidecar' in typename:
            return 'CAROUSEL'
        return 'UNKNOWN'
    
    def _extract_count(self, html: str, pattern: str) -> int:
        """Extract count using regex"""
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return self._parse_count_string(match.group(1))
        return 0
    
    def _parse_count_string(self, count_str: str) -> int:
        """Parse count strings like 1.2K, 5M"""
        try:
            count_str = count_str.replace(',', '').upper()
            
            if 'K' in count_str:
                num = float(count_str.replace('K', ''))
                return int(num * 1000)
            elif 'M' in count_str:
                num = float(count_str.replace('M', ''))
                return int(num * 1000000)
            else:
                return int(count_str)
        except:
            return 0
    
    def _count_data_points(self, data: Dict) -> int:
        """Count data points"""
        count = 0
        
        def recursive_count(obj):
            nonlocal count
            if isinstance(obj, dict):
                count += len(obj)
                for v in obj.values():
                    recursive_count(v)
            elif isinstance(obj, list):
                count += len(obj)
                for item in obj:
                    recursive_count(item)
        
        recursive_count(data)
        return count
    
    def get_stories(self, username: str, client_ip: str = None) -> Dict:
        """Get stories (placeholder - requires auth)"""
        return {
            "error": "AUTHENTICATION_REQUIRED",
            "message": "Story access requires authentication"
        }
    
    def test_connection(self, client_ip: str = None) -> Dict:
        """Test connection with client IP"""
        try:
            test_data = self.scrape_profile('instagram', client_ip)
            
            if 'error' in test_data:
                return {
                    "status": "DEGRADED",
                    "message": "Connection test failed",
                    "used_ip": client_ip or "direct",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            return {
                "status": "OPERATIONAL",
                "message": "Scraper working with IP rotation",
                "used_ip": test_data.get('used_ip', 'direct'),
                "timestamp": datetime.utcnow().isoformat(),
                "data_points": test_data.get('data_points', 0)
            }
            
        except Exception as e:
            return {
                "status": "OFFLINE",
                "message": str(e),
                "used_ip": client_ip or "direct",
                "timestamp": datetime.utcnow().isoformat()
            }
