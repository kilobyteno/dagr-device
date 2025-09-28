#!/usr/bin/env python3
"""
Dagr Update Manager
Handles downloading and applying updates to the Dagr system
"""

import os
import sys
import json
import shutil
import tarfile
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
import requests
import logging

from version import version_manager

logger = logging.getLogger(__name__)

class UpdateManager:
    """Manages system updates for Dagr"""
    
    def __init__(self):
        self.project_root = Path(os.getenv("PROJECT_DIR", "/usr/local/dagr"))
        self.src_dir = Path(os.getenv("SRC_DIR", self.project_root / "src"))
        self.config_dir = Path(os.getenv("DAGR_CONFIG_DIR", self.project_root / "config"))
        
        # Backup directory
        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Update configuration
        self.update_config_file = self.config_dir / "update_config.json"
        self.update_config = self.load_update_config()
    
    def load_update_config(self) -> Dict:
        """Load update configuration"""
        if self.update_config_file.exists():
            try:
                with open(self.update_config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load update config: {e}")
        
        # Default update configuration
        default_config = {
            "auto_update": False,
            "update_channel": "stable",
            "backup_before_update": True,
            "restart_after_update": True,
            "update_url": "https://api.github.com/repos/your-org/dagr-device/releases/latest",
            "excluded_files": [
                "config/*.json",
                "config/tokens.json",
                "config/.key",
                "config/backups/*"
            ],
            "critical_files": [
                "src/dagr.py",
                "src/display_manager.py",
                "src/version.py",
                "install/install.sh",
                "install/dagr.service"
            ]
        }
        
        # Save default config
        try:
            with open(self.update_config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save default update config: {e}")
        
        return default_config
    
    def save_update_config(self):
        """Save update configuration"""
        try:
            with open(self.update_config_file, 'w') as f:
                json.dump(self.update_config, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save update config: {e}")
    
    def create_backup(self, backup_name: str = None) -> Path:
        """Create a backup of the current installation"""
        if not backup_name:
            from datetime import datetime
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(exist_ok=True)
        
        logger.info(f"Creating backup: {backup_path}")
        
        try:
            # Backup critical files and directories
            critical_paths = [
                self.src_dir,
                self.project_root / "install",
                self.project_root / "VERSION"
            ]
            
            for path in critical_paths:
                if path.exists():
                    if path.is_file():
                        shutil.copy2(path, backup_path / path.name)
                    else:
                        shutil.copytree(path, backup_path / path.name, dirs_exist_ok=True)
            
            # Create backup manifest
            manifest = {
                "backup_date": backup_name,
                "version": version_manager.current_version,
                "git_commit": version_manager.get_git_commit_hash(),
                "files": [str(p.relative_to(backup_path)) for p in backup_path.rglob("*") if p.is_file()]
            }
            
            with open(backup_path / "manifest.json", 'w') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"Backup created successfully: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # Clean up partial backup
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            raise
    
    def download_update(self, download_url: str) -> Path:
        """Download update package"""
        logger.info(f"Downloading update from: {download_url}")
        
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix="dagr_update_"))
        
        try:
            # Determine filename from URL
            filename = download_url.split("/")[-1]
            if not filename.endswith((".tar.gz", ".zip")):
                filename = "update.tar.gz"
            
            download_path = temp_dir / filename
            
            # Download with progress
            response = requests.get(download_url, stream=True, timeout=300)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            logger.info(f"Download progress: {progress:.1f}%")
            
            logger.info(f"Download completed: {download_path}")
            return download_path
            
        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            # Clean up
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    
    def extract_update(self, archive_path: Path) -> Path:
        """Extract update archive"""
        logger.info(f"Extracting update: {archive_path}")
        
        extract_dir = archive_path.parent / "extracted"
        extract_dir.mkdir(exist_ok=True)
        
        try:
            if archive_path.suffix == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif archive_path.name.endswith('.tar.gz'):
                with tarfile.open(archive_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                raise ValueError(f"Unsupported archive format: {archive_path}")
            
            logger.info(f"Extraction completed: {extract_dir}")
            return extract_dir
            
        except Exception as e:
            logger.error(f"Failed to extract update: {e}")
            raise
    
    def validate_update(self, update_dir: Path) -> bool:
        """Validate update package"""
        logger.info("Validating update package")
        
        try:
            # Check for VERSION file
            version_file = None
            for vf in update_dir.rglob("VERSION"):
                version_file = vf
                break
            
            if not version_file:
                logger.error("No VERSION file found in update")
                return False
            
            # Check version
            with open(version_file, 'r') as f:
                update_version = f.read().strip()
            
            if not version_manager.is_newer_version_available(update_version):
                logger.error(f"Update version {update_version} is not newer than current {version_manager.current_version}")
                return False
            
            # Check for critical files
            critical_files = self.update_config.get("critical_files", [])
            for critical_file in critical_files:
                found = False
                for cf in update_dir.rglob(Path(critical_file).name):
                    found = True
                    break
                if not found:
                    logger.warning(f"Critical file not found in update: {critical_file}")
            
            logger.info("Update package validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Update validation failed: {e}")
            return False
    
    def apply_update(self, update_dir: Path) -> bool:
        """Apply the update"""
        logger.info("Applying update")
        
        try:
            # Create backup if configured
            if self.update_config.get("backup_before_update", True):
                self.create_backup()
            
            # Stop services
            self.stop_services()
            
            # Find the actual update content (might be in a subdirectory)
            update_root = update_dir
            for subdir in update_dir.iterdir():
                if subdir.is_dir() and (subdir / "VERSION").exists():
                    update_root = subdir
                    break
            
            # Copy files
            excluded_patterns = self.update_config.get("excluded_files", [])
            
            for src_path in update_root.rglob("*"):
                if src_path.is_file():
                    # Calculate relative path
                    rel_path = src_path.relative_to(update_root)
                    
                    # Check if file should be excluded
                    should_exclude = False
                    for pattern in excluded_patterns:
                        if rel_path.match(pattern) or str(rel_path).startswith(pattern.replace("*", "")):
                            should_exclude = True
                            break
                    
                    if should_exclude:
                        logger.debug(f"Skipping excluded file: {rel_path}")
                        continue
                    
                    # Determine destination
                    dest_path = self.project_root / rel_path
                    
                    # Create destination directory
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(src_path, dest_path)
                    logger.debug(f"Updated: {rel_path}")
            
            # Update version
            version_file = update_root / "VERSION"
            if version_file.exists():
                with open(version_file, 'r') as f:
                    new_version = f.read().strip()
                version_manager.set_version(new_version)
            
            # Set proper ownership and permissions for all files
            import subprocess
            try:
                # Set ownership to root
                subprocess.run(["chown", "-R", "root:root", str(self.project_root)], check=True)
                
                # Set permissions for Python files
                subprocess.run(["find", str(self.src_dir), "-type", "f", "-name", "*.py", "-exec", "chmod", "644", "{}", ";"], check=False)
                
                # Set executable permissions for scripts
                executable_files = [
                    self.project_root / "install" / "dagr",
                    self.src_dir / "dagr_display",
                    self.src_dir / "dagr_update"
                ]
                
                for exe_file in executable_files:
                    if exe_file.exists():
                        exe_file.chmod(0o755)
                        
                logger.info("Permissions updated successfully")
            except Exception as e:
                logger.warning(f"Could not update permissions: {e}")
            
            logger.info("Update applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply update: {e}")
            return False
    
    def stop_services(self):
        """Stop Dagr services before update"""
        logger.info("Stopping services for update")
        
        try:
            # Stop systemd service
            subprocess.run(["systemctl", "stop", "dagr"], check=False)
            logger.info("Stopped dagr service")
        except Exception as e:
            logger.warning(f"Could not stop systemd service: {e}")
    
    def start_services(self):
        """Start Dagr services after update"""
        logger.info("Starting services after update")
        
        try:
            # Start systemd service
            subprocess.run(["systemctl", "start", "dagr"], check=False)
            logger.info("Started dagr service")
        except Exception as e:
            logger.warning(f"Could not start systemd service: {e}")
    
    def perform_update(self, download_url: str) -> Dict:
        """Perform complete update process"""
        logger.info("Starting update process")
        
        temp_dir = None
        try:
            # Download update
            archive_path = self.download_update(download_url)
            temp_dir = archive_path.parent
            
            # Extract update
            update_dir = self.extract_update(archive_path)
            
            # Validate update
            if not self.validate_update(update_dir):
                return {"success": False, "error": "Update validation failed"}
            
            # Apply update
            if not self.apply_update(update_dir):
                return {"success": False, "error": "Failed to apply update"}
            
            # Restart services if configured
            if self.update_config.get("restart_after_update", True):
                self.start_services()
            
            logger.info("Update process completed successfully")
            return {
                "success": True,
                "message": "Update completed successfully",
                "new_version": version_manager.current_version
            }
            
        except Exception as e:
            logger.error(f"Update process failed: {e}")
            return {"success": False, "error": str(e)}
        
        finally:
            # Clean up temporary files
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def rollback_to_backup(self, backup_name: str) -> bool:
        """Rollback to a previous backup"""
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_name}")
            return False
        
        logger.info(f"Rolling back to backup: {backup_name}")
        
        try:
            # Stop services
            self.stop_services()
            
            # Load backup manifest
            manifest_file = backup_path / "manifest.json"
            if manifest_file.exists():
                with open(manifest_file, 'r') as f:
                    manifest = json.load(f)
                logger.info(f"Rolling back to version: {manifest.get('version', 'unknown')}")
            
            # Restore files
            for src_path in backup_path.rglob("*"):
                if src_path.is_file() and src_path.name != "manifest.json":
                    rel_path = src_path.relative_to(backup_path)
                    dest_path = self.project_root / rel_path
                    
                    # Create destination directory
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(src_path, dest_path)
            
            # Update version manager
            version_manager.current_version = version_manager.get_current_version()
            
            # Restart services
            self.start_services()
            
            logger.info("Rollback completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    def list_backups(self) -> List[Dict]:
        """List available backups"""
        backups = []
        
        for backup_dir in self.backup_dir.iterdir():
            if backup_dir.is_dir():
                manifest_file = backup_dir / "manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, 'r') as f:
                            manifest = json.load(f)
                        backups.append({
                            "name": backup_dir.name,
                            "date": manifest.get("backup_date"),
                            "version": manifest.get("version"),
                            "git_commit": manifest.get("git_commit"),
                            "file_count": len(manifest.get("files", []))
                        })
                    except Exception as e:
                        logger.warning(f"Could not read backup manifest: {e}")
        
        return sorted(backups, key=lambda x: x["date"], reverse=True)

# Global update manager instance
update_manager = UpdateManager()
