#!/usr/bin/env python3
"""
Dagr Version Management
Handles version checking, comparison, and update detection
"""

import os
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Optional, Tuple
from packaging import version
from datetime import datetime

logger = logging.getLogger(__name__)

class VersionManager:
    """Manages version information and updates for Dagr"""
    
    def __init__(self):
        self.project_root = Path(os.getenv("PROJECT_DIR", "/usr/local/dagr"))
        self.src_dir = Path(os.getenv("SRC_DIR", self.project_root / "src"))
        self.config_dir = Path(os.getenv("DAGR_CONFIG_DIR", self.project_root / "config"))
        
        # Version files
        self.version_file = self.project_root / "VERSION"
        self.version_info_file = self.config_dir / "version_info.json"
        
        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load current version info
        self.current_version = self.get_current_version()
        self.version_info = self.load_version_info()
    
    def get_current_version(self) -> str:
        """Get the current version from VERSION file"""
        try:
            if self.version_file.exists():
                with open(self.version_file, 'r') as f:
                    return f.read().strip()
            else:
                logger.warning("VERSION file not found, defaulting to 0.0.0")
                return "0.0.0"
        except Exception as e:
            logger.error(f"Error reading version file: {e}")
            return "0.0.0"
    
    def load_version_info(self) -> Dict:
        """Load extended version information"""
        if self.version_info_file.exists():
            try:
                with open(self.version_info_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load version info: {e}")
        
        # Default version info
        return {
            "version": self.current_version,
            "build_date": datetime.now().isoformat(),
            "git_commit": None,
            "update_channel": "stable",
            "last_update_check": None,
            "available_version": None
        }
    
    def save_version_info(self):
        """Save version information to file"""
        try:
            with open(self.version_info_file, 'w') as f:
                json.dump(self.version_info, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save version info: {e}")
    
    def update_version_info(self, **kwargs):
        """Update version information"""
        self.version_info.update(kwargs)
        self.save_version_info()
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings
        Returns: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        try:
            v1 = version.parse(version1)
            v2 = version.parse(version2)
            
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0
        except Exception as e:
            logger.error(f"Error comparing versions {version1} and {version2}: {e}")
            return 0
    
    def is_newer_version_available(self, remote_version: str) -> bool:
        """Check if a newer version is available"""
        return self.compare_versions(self.current_version, remote_version) < 0
    
    def get_git_commit_hash(self) -> Optional[str]:
        """Get current git commit hash if available"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not get git commit: {e}")
        return None
    
    def check_for_updates(self, update_url: str = None) -> Dict:
        """
        Check for available updates
        Returns dict with update information
        """
        if not update_url:
            # Default update URL (you can customize this)
            update_url = "https://api.github.com/repos/kilobyteno/dagr-device/releases/latest"
        
        try:
            logger.info("Checking for updates...")
            response = requests.get(update_url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            remote_version = release_data.get("tag_name", "").lstrip("v")
            
            update_info = {
                "current_version": self.current_version,
                "remote_version": remote_version,
                "update_available": self.is_newer_version_available(remote_version),
                "release_date": release_data.get("published_at"),
                "release_notes": release_data.get("body", ""),
                "download_url": None,
                "last_checked": datetime.now().isoformat()
            }
            
            # Find download URL for the release
            assets = release_data.get("assets", [])
            for asset in assets:
                if asset.get("name", "").endswith((".tar.gz", ".zip")):
                    update_info["download_url"] = asset.get("browser_download_url")
                    break
            
            # Update version info
            self.update_version_info(
                last_update_check=update_info["last_checked"],
                available_version=remote_version if update_info["update_available"] else None
            )
            
            logger.info(f"Update check complete. Current: {self.current_version}, Available: {remote_version}")
            return update_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error checking for updates: {e}")
            return {
                "error": f"Network error: {str(e)}",
                "current_version": self.current_version,
                "last_checked": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return {
                "error": f"Update check failed: {str(e)}",
                "current_version": self.current_version,
                "last_checked": datetime.now().isoformat()
            }
    
    def get_version_info(self) -> Dict:
        """Get comprehensive version information"""
        git_commit = self.get_git_commit_hash()
        
        info = {
            "version": self.current_version,
            "git_commit": git_commit,
            "build_date": self.version_info.get("build_date"),
            "update_channel": self.version_info.get("update_channel", "stable"),
            "last_update_check": self.version_info.get("last_update_check"),
            "available_version": self.version_info.get("available_version"),
            "update_available": False
        }
        
        # Check if update is available
        if info["available_version"]:
            info["update_available"] = self.is_newer_version_available(info["available_version"])
        
        return info
    
    def set_version(self, new_version: str):
        """Set a new version (used during updates)"""
        try:
            with open(self.version_file, 'w') as f:
                f.write(new_version)
            
            self.current_version = new_version
            self.update_version_info(
                version=new_version,
                build_date=datetime.now().isoformat(),
                git_commit=self.get_git_commit_hash()
            )
            
            logger.info(f"Version updated to {new_version}")
            
        except Exception as e:
            logger.error(f"Error setting version: {e}")
            raise

# Global version manager instance
version_manager = VersionManager()

def get_version() -> str:
    """Get current version string"""
    return version_manager.current_version

def get_version_info() -> Dict:
    """Get comprehensive version information"""
    return version_manager.get_version_info()

def check_for_updates(update_url: str = None) -> Dict:
    """Check for available updates"""
    return version_manager.check_for_updates(update_url)

def is_update_available() -> bool:
    """Quick check if update is available"""
    info = version_manager.get_version_info()
    return info.get("update_available", False)
