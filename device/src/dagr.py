#!/usr/bin/env python3
"""
Dagr - Device
A FastAPI web application for managing external API tokens and display content.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, Form, Request, HTTPException, Depends, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl
from cryptography.fernet import Fernet
import uvicorn
from display_manager import DisplayManager
from version import get_version, get_version_info, check_for_updates
from update_manager import update_manager

# Configuration
CONFIG_DIR = Path(os.getenv("DAGR_CONFIG_DIR", "/usr/local/dagr/config"))
TOKEN_FILE = CONFIG_DIR / "tokens.json"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "dagr.log"

# Ensure config directory exists
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("dagr")

# Security
security = HTTPBearer(auto_error=False)

class TokenData(BaseModel):
    """Token data model"""
    token: str
    api_url: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    last_used: Optional[datetime] = None

class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str

class TokenManager:
    """Manages API tokens with encryption"""
    
    def __init__(self):
        self.key_file = CONFIG_DIR / ".key"
        self.cipher = self._get_or_create_cipher()
    
    def _get_or_create_cipher(self) -> Fernet:
        """Get or create encryption cipher"""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            os.chmod(self.key_file, 0o600)  # Secure permissions
        return Fernet(key)
    
    def save_token(self, service_name: str, token_data: TokenData) -> None:
        """Save encrypted token data"""
        tokens = self.load_tokens()
        
        # Encrypt sensitive data
        encrypted_token = self.cipher.encrypt(token_data.token.encode()).decode()
        
        tokens[service_name] = {
            "token": encrypted_token,
            "api_url": str(token_data.api_url),
            "expires_at": token_data.expires_at.isoformat() if token_data.expires_at else None,
            "created_at": token_data.created_at.isoformat(),
            "last_used": token_data.last_used.isoformat() if token_data.last_used else None
        }
        
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        
        logger.info(f"Token saved for service: {service_name}")
    
    def load_tokens(self) -> Dict[str, Any]:
        """Load all tokens"""
        if not TOKEN_FILE.exists():
            return {}
        
        try:
            with open(TOKEN_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning("Could not load tokens file, returning empty dict")
            return {}
    
    def get_token(self, service_name: str) -> Optional[TokenData]:
        """Get decrypted token data"""
        tokens = self.load_tokens()
        if service_name not in tokens:
            return None
        
        token_info = tokens[service_name]
        try:
            # Decrypt token
            decrypted_token = self.cipher.decrypt(token_info["token"].encode()).decode()
            
            # Parse dates
            expires_at = None
            if token_info.get("expires_at"):
                expires_at = datetime.fromisoformat(token_info["expires_at"])
            
            created_at = datetime.fromisoformat(token_info["created_at"])
            last_used = None
            if token_info.get("last_used"):
                last_used = datetime.fromisoformat(token_info["last_used"])
            
            return TokenData(
                token=decrypted_token,
                api_url=token_info["api_url"],
                expires_at=expires_at,
                created_at=created_at,
                last_used=last_used
            )
        except Exception as e:
            logger.error(f"Error decrypting token for {service_name}: {e}")
            return None
    
    def update_last_used(self, service_name: str) -> None:
        """Update last used timestamp"""
        tokens = self.load_tokens()
        if service_name in tokens:
            tokens[service_name]["last_used"] = datetime.now().isoformat()
            with open(TOKEN_FILE, 'w') as f:
                json.dump(tokens, f, indent=2)
    
    def delete_token(self, service_name: str) -> bool:
        """Delete a token"""
        tokens = self.load_tokens()
        if service_name in tokens:
            del tokens[service_name]
            with open(TOKEN_FILE, 'w') as f:
                json.dump(tokens, f, indent=2)
            logger.info(f"Token deleted for service: {service_name}")
            return True
        return False
    
    def is_token_valid(self, service_name: str) -> bool:
        """Check if token is valid and not expired"""
        token_data = self.get_token(service_name)
        if not token_data:
            return False
        
        if token_data.expires_at and token_data.expires_at < datetime.now():
            logger.warning(f"Token expired for service: {service_name}")
            return False
        
        return True

# Global token manager, display manager, and config
token_manager = TokenManager()
display_manager = None
app_config = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global app_config, display_manager
    logger.info("Starting Dagr application")
    
    # Load configuration
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                app_config = json.load(f)
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load config file: {e}")
            app_config = {}
    
    # Initialize display manager
    try:
        display_manager = DisplayManager()
        # Start automatic image rotation if enabled
        display_config = app_config.get("display", {})
        if display_config.get("auto_refresh", True):
            display_manager.start_rotation()
            logger.info("Display rotation started automatically")
    except Exception as e:
        logger.warning(f"Could not initialize display manager: {e}")
        display_manager = None
    
    yield
    
    # Cleanup
    if display_manager:
        display_manager.stop_rotation()
        logger.info("Display rotation stopped")
    
    logger.info("Shutting down Dagr application")

# FastAPI app
app = FastAPI(
    title="Dagr",
    description="Device",
    version=get_version(),
    lifespan=lifespan
)

# Templates setup
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Create templates directory and basic template if it doesn't exist
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)

# Basic HTML template
login_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dagr - Device</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; color: #555; }
        input, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
        button { background: #007bff; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .alert { padding: 15px; margin: 20px 0; border-radius: 5px; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .token-list { margin-top: 30px; }
        .token-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }
        .token-actions { margin-top: 10px; }
        .btn-small { padding: 5px 15px; font-size: 14px; margin-right: 10px; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Dagr - Device</h1>
        
        {% if message %}
        <div class="alert alert-{{ message_type }}">{{ message }}</div>
        {% endif %}
        
        <form method="post" action="/login">
            <div class="form-group">
                <label for="username">Username/Email:</label>
                <input type="text" id="username" name="username" required>
            </div>
            
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <button type="submit">Login</button>
        </form>
        
        <div style="margin-top: 20px; padding: 15px; background: #e9ecef; border-radius: 5px;">
            <h3>API Configuration</h3>
            <p><strong>API URL:</strong> {{ api_config.base_url if api_config else "Not configured" }}</p>
            <p><strong>Login Endpoint:</strong> {{ api_config.login_endpoint if api_config else "Not configured" }}</p>
        </div>
        
        <div class="display-controls" style="margin-top: 30px;">
            <h2>Display Management</h2>
            <div style="display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;">
                <button onclick="nextImage()" class="btn-small">Next Image</button>
                <button onclick="startRotation()" class="btn-small">Start Rotation</button>
                <button onclick="stopRotation()" class="btn-small btn-danger">Stop Rotation</button>
                <button onclick="refreshStatus()" class="btn-small">Refresh Status</button>
            </div>
            <div id="display-status" style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                Loading display status...
            </div>
            
            <div class="image-upload" style="background: #f8f9fa; padding: 20px; border-radius: 5px;">
                <h3>Upload Image</h3>
                <form id="upload-form" enctype="multipart/form-data">
                    <div class="form-group">
                        <label for="image-file">Choose Image File (PNG, JPG, etc.):</label>
                        <input type="file" id="image-file" name="file" accept="image/*" required>
                    </div>
                    <button type="submit" style="margin-top: 10px;">Upload Image</button>
                </form>
                <div id="upload-status" style="margin-top: 10px;"></div>
            </div>
        </div>

        <div class="token-list">
            <h2>Saved Tokens</h2>
            {% if tokens %}
                {% for service_name, token_info in tokens.items() %}
                <div class="token-item">
                    <h3>{{ service_name }}</h3>
                    <p><strong>API URL:</strong> {{ token_info.api_url }}</p>
                    <p><strong>Created:</strong> {{ token_info.created_at }}</p>
                    {% if token_info.expires_at %}
                    <p><strong>Expires:</strong> {{ token_info.expires_at }}</p>
                    {% endif %}
                    {% if token_info.last_used %}
                    <p><strong>Last Used:</strong> {{ token_info.last_used }}</p>
                    {% endif %}
                    <div class="token-actions">
                        <form method="post" action="/test-token/{{ service_name }}" style="display: inline;">
                            <button type="submit" class="btn-small">Test Token</button>
                        </form>
                        <form method="post" action="/delete-token/{{ service_name }}" style="display: inline;">
                            <button type="submit" class="btn-small btn-danger" onclick="return confirm('Are you sure?')">Delete</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p>No tokens saved yet.</p>
            {% endif %}
        </div>
        
        <script>
        async function nextImage() {
            try {
                const response = await fetch('/api/display/next', { method: 'POST' });
                const result = await response.json();
                if (response.ok) {
                    showMessage(result.message, 'success');
                    refreshStatus();
                } else {
                    showMessage(result.detail || 'Failed to show next image', 'error');
                }
            } catch (error) {
                showMessage('Error: ' + error.message, 'error');
            }
        }
        
        async function startRotation() {
            try {
                const response = await fetch('/api/display/start', { method: 'POST' });
                const result = await response.json();
                if (response.ok) {
                    showMessage(result.message, 'success');
                    refreshStatus();
                } else {
                    showMessage(result.detail || 'Failed to start rotation', 'error');
                }
            } catch (error) {
                showMessage('Error: ' + error.message, 'error');
            }
        }
        
        async function stopRotation() {
            try {
                const response = await fetch('/api/display/stop', { method: 'POST' });
                const result = await response.json();
                if (response.ok) {
                    showMessage(result.message, 'success');
                    refreshStatus();
                } else {
                    showMessage(result.detail || 'Failed to stop rotation', 'error');
                }
            } catch (error) {
                showMessage('Error: ' + error.message, 'error');
            }
        }
        
        async function refreshStatus() {
            try {
                const response = await fetch('/api/display/status');
                const status = await response.json();
                
                if (response.ok) {
                    const statusDiv = document.getElementById('display-status');
                    statusDiv.innerHTML = `
                        <h3>Display Status</h3>
                        <p><strong>Display:</strong> ${status.display_connected ? 'Connected (' + status.display_type + ')' : 'Simulation Mode'}</p>
                        ${status.display_connected ? '<p><strong>Resolution:</strong> ' + status.display_resolution + '</p>' : ''}
                        ${status.display_connected ? '<p><strong>Color Mode:</strong> ' + status.color_mode + '</p>' : ''}
                        <p><strong>Rotation:</strong> ${status.rotation_running ? 'Running' : 'Stopped'}</p>
                        <p><strong>Interval:</strong> ${status.rotation_interval} seconds</p>
                        <p><strong>Images:</strong> ${status.total_images} found</p>
                        <p><strong>Current:</strong> ${status.current_image_index + 1}/${status.total_images}</p>
                        <p><strong>Demo Directory:</strong> ${status.demo_directory}</p>
                        ${status.images.length > 0 ? 
                            '<p><strong>Available Images:</strong> ' + status.images.join(', ') + '</p>' : 
                            '<p><em>No images found in demo directory</em></p>'
                        }
                    `;
                } else {
                    document.getElementById('display-status').innerHTML = 
                        '<p style="color: red;">Failed to load display status</p>';
                }
            } catch (error) {
                document.getElementById('display-status').innerHTML = 
                    '<p style="color: red;">Error loading status: ' + error.message + '</p>';
            }
        }
        
        function showMessage(message, type) {
            // Simple message display - could be enhanced with better styling
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type}`;
            alertDiv.textContent = message;
            alertDiv.style.position = 'fixed';
            alertDiv.style.top = '20px';
            alertDiv.style.right = '20px';
            alertDiv.style.zIndex = '1000';
            alertDiv.style.minWidth = '300px';
            
            document.body.appendChild(alertDiv);
            
            setTimeout(() => {
                alertDiv.remove();
            }, 3000);
        }
        
        // Handle image upload
        document.getElementById('upload-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('image-file');
            const file = fileInput.files[0];
            const statusDiv = document.getElementById('upload-status');
            
            if (!file) {
                statusDiv.innerHTML = '<p style="color: red;">Please select a file</p>';
                return;
            }
            
            const formData = new FormData();
            formData.append('file', file);
            
            statusDiv.innerHTML = '<p>Uploading...</p>';
            
            try {
                const response = await fetch('/api/display/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    statusDiv.innerHTML = `<p style="color: green;">${result.message}</p>`;
                    fileInput.value = ''; // Clear the input
                    refreshStatus(); // Refresh display status to show new image
                } else {
                    statusDiv.innerHTML = `<p style="color: red;">Upload failed: ${result.detail}</p>`;
                }
            } catch (error) {
                statusDiv.innerHTML = `<p style="color: red;">Upload error: ${error.message}</p>`;
            }
        });
        
        // Load status on page load
        document.addEventListener('DOMContentLoaded', refreshStatus);
        </script>
    </div>
</body>
</html>
'''

# Write template file
with open(templates_dir / "login.html", "w") as f:
    f.write(login_template)

def make_api_request(url: str, method: str = "GET", headers: Dict = None, data: Dict = None) -> Dict:
    """Make HTTP request to external API"""
    try:
        # Get timeout from config
        api_config = app_config.get("external_api", {})
        timeout = api_config.get("timeout", 30)
        
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as e:
        logger.error(f"Request timeout: {e}")
        raise HTTPException(status_code=408, detail="API request timed out")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(status_code=503, detail="Unable to connect to API")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        raise HTTPException(status_code=400, detail=f"API request failed: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=400, detail=f"API request failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, message: str = None, message_type: str = "success"):
    """Display login form and token management page"""
    tokens = token_manager.load_tokens()
    api_config = app_config.get("external_api", {})
    return templates.TemplateResponse(
        "login.html", 
        {
            "request": request, 
            "tokens": tokens, 
            "message": message, 
            "message_type": message_type,
            "api_config": api_config
        }
    )

@app.post("/login")
async def login_and_save_token(
    username: str = Form(...),
    password: str = Form(...)
):
    """Login to external API and save token"""
    try:
        # Get API configuration
        api_config = app_config.get("external_api", {})
        if not api_config.get("base_url"):
            raise HTTPException(status_code=500, detail="External API not configured")
        
        api_url = api_config["base_url"]
        token_endpoint = api_config.get("login_endpoint", "/auth/login")
        token_field = api_config.get("token_field", "access_token")
        
        # Construct full login URL
        login_url = f"{api_url.rstrip('/')}{token_endpoint}"
        
        # Prepare login data
        login_data = {
            "username": username,
            "password": password
        }
        
        # Make login request
        logger.info(f"Attempting login to {login_url}")
        response_data = make_api_request(login_url, "POST", data=login_data)
        
        # Extract token from response
        token = None
        # First try the configured token field
        if token_field in response_data:
            token = response_data[token_field]
        else:
            # Fallback to common field names
            for field in ["token", "access_token", "jwt", "auth_token", "api_key"]:
                if field in response_data:
                    token = response_data[field]
                    break
        
        if not token:
            raise HTTPException(status_code=400, detail="No token found in API response")
        
        # Parse expiration if available
        expires_at = None
        if "expires_at" in response_data:
            expires_at = datetime.fromisoformat(response_data["expires_at"])
        elif "expires_in" in response_data:
            expires_at = datetime.now() + timedelta(seconds=int(response_data["expires_in"]))
        
        # Use username as service name (or could be hardcoded)
        service_name = username
        
        # Save token
        token_data = TokenData(
            token=token,
            api_url=api_url,
            expires_at=expires_at,
            created_at=datetime.now()
        )
        
        token_manager.save_token(service_name, token_data)
        
        return RedirectResponse(
            url=f"/?message=Token saved successfully for {service_name}&message_type=success",
            status_code=303
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        return RedirectResponse(
            url=f"/?message=Login failed: {str(e)}&message_type=error",
            status_code=303
        )

@app.post("/test-token/{service_name}")
async def test_token(service_name: str):
    """Test if a saved token is valid"""
    try:
        token_data = token_manager.get_token(service_name)
        if not token_data:
            return RedirectResponse(
                url=f"/?message=Token not found for {service_name}&message_type=error",
                status_code=303
            )
        
        # Get test endpoint from configuration
        api_config = app_config.get("external_api", {})
        test_endpoint = api_config.get("test_endpoint", "/user/profile")
        
        # Test token with configured endpoint
        test_url = f"{token_data.api_url.rstrip('/')}{test_endpoint}"
        headers = {"Authorization": f"Bearer {token_data.token}"}
        
        make_api_request(test_url, "GET", headers=headers)
        
        # Update last used timestamp
        token_manager.update_last_used(service_name)
        
        return RedirectResponse(
            url=f"/?message=Token for {service_name} is valid and working&message_type=success",
            status_code=303
        )
        
    except HTTPException as e:
        return RedirectResponse(
            url=f"/?message=Token test failed for {service_name}: {e.detail}&message_type=error",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Token test error: {e}")
        return RedirectResponse(
            url=f"/?message=Token test failed for {service_name}: {str(e)}&message_type=error",
            status_code=303
        )

@app.post("/delete-token/{service_name}")
async def delete_token(service_name: str):
    """Delete a saved token"""
    if token_manager.delete_token(service_name):
        return RedirectResponse(
            url=f"/?message=Token deleted for {service_name}&message_type=success",
            status_code=303
        )
    else:
        return RedirectResponse(
            url=f"/?message=Token not found for {service_name}&message_type=error",
            status_code=303
        )

@app.get("/api/tokens")
async def list_tokens():
    """API endpoint to list all saved tokens (without sensitive data)"""
    tokens = token_manager.load_tokens()
    safe_tokens = {}
    
    for service_name, token_info in tokens.items():
        safe_tokens[service_name] = {
            "api_url": token_info["api_url"],
            "created_at": token_info["created_at"],
            "expires_at": token_info.get("expires_at"),
            "last_used": token_info.get("last_used"),
            "is_valid": token_manager.is_token_valid(service_name)
        }
    
    return safe_tokens

@app.get("/api/request/{service_name}")
async def make_authenticated_request(
    service_name: str,
    endpoint: str,
    method: str = "GET"
):
    """Make an authenticated request using a saved token"""
    token_data = token_manager.get_token(service_name)
    if not token_data:
        raise HTTPException(status_code=404, detail=f"Token not found for service: {service_name}")
    
    if not token_manager.is_token_valid(service_name):
        raise HTTPException(status_code=401, detail=f"Token expired or invalid for service: {service_name}")
    
    # Construct full URL
    url = f"{token_data.api_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token_data.token}"}
    
    try:
        response_data = make_api_request(url, method, headers=headers)
        
        # Update last used timestamp
        token_manager.update_last_used(service_name)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authenticated request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/display/status")
async def display_status():
    """Get display status"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    return display_manager.get_status_dict()

@app.post("/api/display/next")
async def display_next_image():
    """Show next image"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    try:
        display_manager.show_next_image()
        return {"status": "success", "message": "Next image displayed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/display/start")
async def start_display_rotation():
    """Start display rotation"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    try:
        display_manager.start_rotation()
        return {"status": "success", "message": "Display rotation started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/display/stop")
async def stop_display_rotation():
    """Stop display rotation"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    try:
        display_manager.stop_rotation()
        return {"status": "success", "message": "Display rotation stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/display/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image to display"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file size (max 10MB)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    
    try:
        # Read the uploaded file
        contents = await file.read()
        
        # Create a temporary image file in the demo directory
        from PIL import Image
        import io
        
        # Load and validate the image
        image = Image.open(io.BytesIO(contents))
        
        # Save to demo directory
        demo_dir = Path(os.getenv("SRC_DIR", "/usr/local/dagr/src")) / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        import uuid
        file_extension = Path(file.filename).suffix or '.png'
        unique_filename = f"uploaded_{uuid.uuid4().hex[:8]}{file_extension}"
        save_path = demo_dir / unique_filename
        
        # Convert to RGB if necessary and save
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.save(save_path, 'PNG')
        
        logger.info(f"Image uploaded and saved: {save_path}")
        
        return {
            "status": "success", 
            "message": f"Image uploaded successfully as {unique_filename}",
            "filename": unique_filename
        }
        
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")

@app.delete("/api/display/image/{filename}")
async def delete_image(filename: str):
    """Delete an uploaded image"""
    if not display_manager:
        raise HTTPException(status_code=503, detail="Display manager not available")
    
    try:
        demo_dir = Path(os.getenv("SRC_DIR", "/usr/local/dagr/src")) / "demo"
        image_path = demo_dir / filename
        
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Don't allow deletion of original demo images
        if filename in ['luna.png', 'odin.png']:
            raise HTTPException(status_code=403, detail="Cannot delete original demo images")
        
        image_path.unlink()
        logger.info(f"Image deleted: {image_path}")
        
        return {"status": "success", "message": f"Image {filename} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")

@app.get("/api/version")
async def version_info():
    """Get version information"""
    return get_version_info()

@app.get("/api/version/check")
async def check_version_updates():
    """Check for available updates"""
    return check_for_updates()

@app.post("/api/version/update")
async def perform_system_update(download_url: str = Form(...)):
    """Perform system update"""
    try:
        result = update_manager.perform_update(download_url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/version/backup")
async def create_system_backup():
    """Create system backup"""
    try:
        backup_path = update_manager.create_backup()
        return {
            "success": True,
            "backup_name": backup_path.name,
            "backup_path": str(backup_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/version/backups")
async def list_system_backups():
    """List available backups"""
    return update_manager.list_backups()

@app.post("/api/version/rollback")
async def rollback_system(backup_name: str = Form(...)):
    """Rollback to backup"""
    try:
        success = update_manager.rollback_to_backup(backup_name)
        if success:
            return {"success": True, "message": f"Rollback to {backup_name} completed"}
        else:
            raise HTTPException(status_code=400, detail="Rollback failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    display_status = "unknown"
    if display_manager:
        display_status = "connected" if display_manager.display else "simulation"
    
    version_info = get_version_info()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "dagr",
        "version": version_info["version"],
        "git_commit": version_info.get("git_commit"),
        "update_available": version_info.get("update_available", False),
        "display": display_status,
        "display_rotation": display_manager.running if display_manager else False
    }

if __name__ == "__main__":
    # Load configuration
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config file: {e}")
    
    # Server configuration
    web_config = config.get("web_server", {})
    host = web_config.get("host", "0.0.0.0")
    port = web_config.get("port", 8000)
    debug = web_config.get("debug", False)
    
    logger.info(f"Starting Dagr server on {host}:{port}")
    
    # Log API configuration
    api_config = config.get("external_api", {})
    if api_config.get("base_url"):
        logger.info(f"External API configured: {api_config['base_url']}")
    else:
        logger.warning("External API not configured in config.json")
    
    uvicorn.run(
        "dagr:app",
        host=host,
        port=port,
        reload=debug,
        access_log=True,
        log_config=None
    )
