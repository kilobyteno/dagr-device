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
        
        # Verify the version system is working
        verify_version_system(project_root, new_version)
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def update_references(project_root, old_version, new_version):
    """Update version references in other files"""
    
    # Files that might contain version references
    files_to_check = [
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
    
    # Note: src/dagr.py now uses get_version() dynamically, so no need to update it

def verify_version_system(project_root, expected_version):
    """Verify that the version system is working correctly"""
    print("\n🔍 Verifying version system...")
    
    try:
        # Add src to path temporarily
        import sys
        src_path = str(project_root / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        # Try to import and get version
        from version import get_version
        actual_version = get_version()
        
        if actual_version == expected_version:
            print(f"✅ Version system working correctly: {actual_version}")
        else:
            print(f"⚠️  Version mismatch - Expected: {expected_version}, Got: {actual_version}")
        
        # Clean up path
        if src_path in sys.path:
            sys.path.remove(src_path)
            
    except ImportError as e:
        print(f"⚠️  Could not verify version system: {e}")
    except Exception as e:
        print(f"⚠️  Version system verification failed: {e}")

if __name__ == "__main__":
    main()
