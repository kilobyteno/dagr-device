#!/usr/bin/env python3
"""
Installation Test Script
Verifies that Dagr is properly installed and configured
"""

import os
import sys
from pathlib import Path
import subprocess
import json

def test_file_exists(file_path, description):
    """Test if a file exists"""
    if Path(file_path).exists():
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} - NOT FOUND")
        return False

def test_executable(file_path, description):
    """Test if a file is executable"""
    path = Path(file_path)
    if path.exists() and os.access(path, os.X_OK):
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} - NOT EXECUTABLE")
        return False

def test_service_status():
    """Test systemd service status"""
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "dagr"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ Service enabled: dagr.service")
            return True
        else:
            print(f"❌ Service not enabled: dagr.service")
            return False
    except Exception as e:
        print(f"❌ Could not check service status: {e}")
        return False

def test_permissions(directory, description):
    """Test directory permissions"""
    path = Path(directory)
    if path.exists():
        stat = path.stat()
        owner_uid = stat.st_uid
        if owner_uid == 0:  # root
            print(f"✅ {description}: Owned by root")
            return True
        else:
            print(f"⚠️  {description}: Not owned by root (UID: {owner_uid})")
            return False
    else:
        print(f"❌ {description}: Directory not found")
        return False

def test_python_imports():
    """Test Python module imports"""
    install_root = Path("/usr/local/dagr")
    src_dir = install_root / "src"
    
    if not src_dir.exists():
        print("❌ Source directory not found, skipping import tests")
        return False
    
    # Add to Python path
    sys.path.insert(0, str(src_dir))
    
    modules_to_test = [
        ("version", "Version management"),
        ("display_manager", "Display manager"),
        ("update_manager", "Update manager")
    ]
    
    success_count = 0
    for module_name, description in modules_to_test:
        try:
            module = __import__(module_name)
            print(f"✅ {description}: Import successful")
            
            # Special test for version module
            if module_name == "version" and hasattr(module, 'get_version'):
                try:
                    version = module.get_version()
                    print(f"   📍 Current version: {version}")
                except Exception as e:
                    print(f"   ⚠️  Could not get version: {e}")
            
            success_count += 1
        except ImportError as e:
            print(f"❌ {description}: Import failed - {e}")
        except Exception as e:
            print(f"⚠️  {description}: Import warning - {e}")
    
    return success_count == len(modules_to_test)

def test_configuration():
    """Test configuration files"""
    config_dir = Path("/usr/local/dagr/config")
    config_file = config_dir / "config.json"
    
    if not config_file.exists():
        print("❌ Configuration file not found")
        return False
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        required_sections = ["display", "web_server", "external_api"]
        missing_sections = []
        
        for section in required_sections:
            if section not in config:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"⚠️  Configuration missing sections: {', '.join(missing_sections)}")
            return False
        else:
            print("✅ Configuration file valid")
            return True
            
    except json.JSONDecodeError as e:
        print(f"❌ Configuration file invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Configuration file error: {e}")
        return False

def test_version_consistency():
    """Test version consistency across the system"""
    install_root = Path("/usr/local/dagr")
    version_file = install_root / "VERSION"
    src_dir = install_root / "src"
    
    if not version_file.exists():
        print("❌ VERSION file not found")
        return False
    
    try:
        # Read VERSION file
        with open(version_file, 'r') as f:
            file_version = f.read().strip()
        print(f"📄 VERSION file: {file_version}")
        
        # Test version module if available
        if src_dir.exists():
            sys.path.insert(0, str(src_dir))
            try:
                from version import get_version
                module_version = get_version()
                print(f"🐍 Version module: {module_version}")
                
                if file_version == module_version:
                    print("✅ Version consistency: FILE ↔ MODULE")
                    return True
                else:
                    print(f"❌ Version mismatch: FILE({file_version}) ≠ MODULE({module_version})")
                    return False
                    
            except ImportError:
                print("⚠️  Could not import version module")
                return False
            except Exception as e:
                print(f"⚠️  Version module error: {e}")
                return False
        else:
            print("⚠️  Source directory not found, cannot test version module")
            return False
            
    except Exception as e:
        print(f"❌ Version consistency test failed: {e}")
        return False

def main():
    """Run all installation tests"""
    print("🔧 Dagr Installation Test")
    print("=" * 40)
    
    tests_passed = 0
    total_tests = 0
    
    # Test critical files
    critical_files = [
        ("/usr/local/dagr/VERSION", "Version file"),
        ("/usr/local/dagr/src/dagr.py", "Main application"),
        ("/usr/local/dagr/src/version.py", "Version manager"),
        ("/usr/local/dagr/src/display_manager.py", "Display manager"),
        ("/usr/local/dagr/src/update_manager.py", "Update manager"),
        ("/usr/local/dagr/config/config.json", "Configuration file"),
        ("/usr/local/bin/dagr", "Main executable"),
        ("/etc/systemd/system/dagr.service", "SystemD service")
    ]
    
    print("\n📁 File Existence Tests:")
    for file_path, description in critical_files:
        if test_file_exists(file_path, description):
            tests_passed += 1
        total_tests += 1
    
    # Test executables
    executables = [
        ("/usr/local/bin/dagr", "Main executable"),
        ("/usr/local/dagr/src/dagr_display", "Display CLI"),
        ("/usr/local/dagr/src/dagr_update", "Update CLI")
    ]
    
    print("\n🔧 Executable Tests:")
    for exe_path, description in executables:
        if test_executable(exe_path, description):
            tests_passed += 1
        total_tests += 1
    
    # Test permissions
    print("\n🔒 Permission Tests:")
    if test_permissions("/usr/local/dagr", "Installation directory"):
        tests_passed += 1
    total_tests += 1
    
    # Test service
    print("\n⚙️  Service Tests:")
    if test_service_status():
        tests_passed += 1
    total_tests += 1
    
    # Test configuration
    print("\n📋 Configuration Tests:")
    if test_configuration():
        tests_passed += 1
    total_tests += 1
    
    # Test Python imports (only if source exists)
    print("\n🐍 Python Import Tests:")
    if test_python_imports():
        tests_passed += 1
    total_tests += 1
    
    # Test version consistency
    print("\n🔢 Version Consistency Tests:")
    if test_version_consistency():
        tests_passed += 1
    total_tests += 1
    
    # Summary
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {tests_passed}/{total_tests} passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Dagr is properly installed.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the installation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
