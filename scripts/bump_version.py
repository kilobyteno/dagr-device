#!/usr/bin/env python3
"""
Version Bump Script
Utility to increment version numbers for Dagr releases
"""

import sys
import re
from pathlib import Path

def parse_version(version_str):
    """Parse version string into components"""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$', version_str.strip())
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix

def format_version(major, minor, patch, suffix=None):
    """Format version components into string"""
    version = f"{major}.{minor}.{patch}"
    if suffix:
        version += f"-{suffix}"
    return version

def bump_version(current_version, bump_type="patch"):
    """Bump version based on type"""
    major, minor, patch, suffix = parse_version(current_version)
    
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    # Remove suffix for release versions
    return format_version(major, minor, patch)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Bump Dagr version")
    parser.add_argument("bump_type", choices=["major", "minor", "patch"], 
                       default="patch", nargs="?", help="Version component to bump")
    parser.add_argument("--dry-run", action="store_true", help="Show new version without updating")
    
    args = parser.parse_args()
    
    # Find VERSION file
    project_root = Path(__file__).parent.parent
    version_file = project_root / "VERSION"
    
    if not version_file.exists():
        print("❌ VERSION file not found")
        sys.exit(1)
    
    # Read current version
    with open(version_file, 'r') as f:
        current_version = f.read().strip()
    
    print(f"Current version: {current_version}")
    
    try:
        # Calculate new version
        new_version = bump_version(current_version, args.bump_type)
        print(f"New version: {new_version}")
        
        if args.dry_run:
            print("🔍 Dry run - no files updated")
            return
        
        # Update VERSION file
        with open(version_file, 'w') as f:
            f.write(new_version)
        
        print(f"✅ Version updated to {new_version}")
        
        # Update other version references if needed
        update_references(project_root, current_version, new_version)
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def update_references(project_root, old_version, new_version):
    """Update version references in other files"""
    
    # Files that might contain version references
    files_to_check = [
        "src/dagr.py",
        "install/dagr.service", 
        "README.md"
    ]
    
    updated_files = []
    
    for file_path in files_to_check:
        full_path = project_root / file_path
        if not full_path.exists():
            continue
        
        try:
            with open(full_path, 'r') as f:
                content = f.read()
            
            # Look for version references
            if old_version in content:
                new_content = content.replace(old_version, new_version)
                
                with open(full_path, 'w') as f:
                    f.write(new_content)
                
                updated_files.append(file_path)
        
        except Exception as e:
            print(f"⚠️  Could not update {file_path}: {e}")
    
    if updated_files:
        print(f"📝 Updated version references in: {', '.join(updated_files)}")

if __name__ == "__main__":
    main()
