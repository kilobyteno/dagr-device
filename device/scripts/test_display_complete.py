#!/usr/bin/env python3
"""
Complete Display Test Script for DAGR
Tests display functionality with improved error handling and multiple display types
"""

import os
import sys
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, '/usr/local/dagr/src')

def test_imports():
    """Test all required imports"""
    print("🔍 Testing imports...")
    
    imports_status = {
        "PIL": False,
        "inky": False,
        "numpy": False
    }
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        imports_status["PIL"] = True
        print("  ✅ PIL (Pillow) imported successfully")
    except ImportError as e:
        print(f"  ❌ PIL import failed: {e}")
    
    try:
        from inky.auto import auto
        imports_status["inky"] = True
        print("  ✅ Inky library imported successfully")
    except ImportError as e:
        print(f"  ⚠️  Inky library not available: {e}")
    
    
    try:
        import numpy as np
        imports_status["numpy"] = True
        print("  ✅ NumPy imported successfully")
    except ImportError as e:
        print(f"  ❌ NumPy import failed: {e}")
    
    return imports_status

def check_device_files():
    """Check required device files for hardware interfaces"""
    print("\n🔧 Checking device files...")
    
    device_files = [
        "/dev/spidev0.0",
        "/dev/spidev0.1",
        "/dev/gpiomem",
        "/sys/class/gpio",
        "/proc/device-tree/soc/spi@7e204000/status",
        "/proc/device-tree/soc/spi@7e215080/status"
    ]
    
    for device_file in device_files:
        if Path(device_file).exists():
            print(f"  ✅ {device_file}")
            
            # Check SPI status specifically
            if "spi" in device_file and "status" in device_file:
                try:
                    with open(device_file, 'r') as f:
                        status = f.read().strip().replace('\x00', '')
                        print(f"      Status: {status}")
                except:
                    pass
        else:
            print(f"  ❌ {device_file} (missing)")

def test_display_manager():
    """Test the DAGR display manager"""
    print("\n📺 Testing DAGR Display Manager...")
    
    try:
        from display_manager import DisplayManager
        print("  ✅ DisplayManager imported successfully")
        
        # Create display manager instance
        dm = DisplayManager()
        print("  ✅ DisplayManager instance created")
        
        # Get status
        status = dm.get_status_dict()
        print(f"  📊 Display Status:")
        for key, value in status.items():
            print(f"      {key}: {value}")
        
        # Test image operations
        images = dm.get_demo_images()
        print(f"  🖼️  Found {len(images)} demo images: {[img.name for img in images]}")
        
        if images:
            print("  🎯 Testing image display...")
            try:
                dm.show_next_image()
                print("  ✅ Image display test completed")
            except Exception as e:
                print(f"  ❌ Image display test failed: {e}")
                import traceback
                print(f"      Traceback: {traceback.format_exc()}")
        else:
            print("  ⚠️  No demo images found - creating placeholder...")
            try:
                dm.create_demo_placeholder()
                print("  ✅ Placeholder created")
            except Exception as e:
                print(f"  ❌ Placeholder creation failed: {e}")
        
        return dm
        
    except Exception as e:
        print(f"  ❌ DisplayManager test failed: {e}")
        import traceback
        print(f"      Traceback: {traceback.format_exc()}")
        return None

def test_inky_direct():
    """Test Inky display directly"""
    print("\n🎨 Testing Inky Display Direct Access...")
    
    try:
        from inky.auto import auto
        from PIL import Image, ImageDraw, ImageFont
        
        # Try auto-detection
        display = auto()
        print(f"  ✅ Inky display detected: {type(display).__name__}")
        print(f"      Resolution: {display.width}x{display.height}")
        print(f"      Color mode: {display.colour}")
        
        # Create test image
        img = Image.new('RGB', (display.width, display.height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Add test content
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        text = "DAGR Test Display"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = (display.width - text_width) // 2
        y = (display.height - text_height) // 2
        
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
        
        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        draw.text((10, display.height - 30), f"Test: {timestamp}", fill=(100, 100, 100))
        
        print("  🖼️  Test image created")
        
        # Display the image
        display.set_image(img)
        print("  ✅ Image set on display")
        
        display.show()
        print("  ✅ Image displayed successfully!")
        
        return True
        
    except SystemExit as e:
        if "pins we need are in use" in str(e):
            print(f"  ⚠️  GPIO conflict: {e}")
            print("  🔧 This indicates SPI configuration issues")
            return False
        else:
            print(f"  ❌ System exit: {e}")
            return False
    except Exception as e:
        print(f"  ❌ Inky direct test failed: {e}")
        import traceback
        print(f"      Traceback: {traceback.format_exc()}")
        return False

def check_spi_configuration():
    """Check SPI configuration"""
    print("\n⚙️  Checking SPI Configuration...")
    
    # Check if SPI is enabled in config
    config_files = ["/boot/firmware/config.txt", "/boot/config.txt"]
    
    for config_file in config_files:
        if Path(config_file).exists():
            print(f"  📄 Checking {config_file}")
            try:
                with open(config_file, 'r') as f:
                    content = f.read()
                    if "dtparam=spi=on" in content and not content.find("dtparam=spi=on").startswith("#"):
                        print("  ✅ SPI enabled in config")
                    else:
                        print("  ❌ SPI not enabled in config")
            except Exception as e:
                print(f"  ❌ Could not read config file: {e}")
            break
    
    # Check loaded kernel modules
    try:
        with open("/proc/modules", 'r') as f:
            modules = f.read()
            if "spi_bcm2835" in modules:
                print("  ✅ SPI kernel module loaded")
            else:
                print("  ❌ SPI kernel module not loaded")
    except Exception as e:
        print(f"  ❌ Could not check kernel modules: {e}")

def main():
    print("🚀 DAGR Complete Display Test")
    print("=" * 50)
    
    # Test imports
    imports = test_imports()
    
    # Check device files
    check_device_files()
    
    # Check SPI configuration
    check_spi_configuration()
    
    # Test display manager
    display_manager = test_display_manager()
    
    # Test Inky direct if available
    if imports.get("inky", False):
        success = test_inky_direct()
        if not success:
            print("\n💡 Troubleshooting Tips:")
            print("   1. Ensure SPI is enabled: sudo raspi-config -> Interface Options -> SPI")
            print("   2. Reboot after enabling SPI: sudo reboot")
            print("   3. Check display connections")
            print("   4. Try running with sudo for GPIO access")
    
    print("\n✨ Test Complete!")
    print("\n📊 Summary:")
    if display_manager and display_manager.display:
        print("  ✅ Display hardware detected and working")
    elif display_manager:
        print("  ⚠️  Display manager working in simulation mode")
    else:
        print("  ❌ Display manager failed to initialize")
    
    if imports.get("PIL", False):
        print("  ✅ Image processing capabilities available")
    else:
        print("  ❌ Image processing not available")

if __name__ == "__main__":
    main()
