#!/usr/bin/env python3
"""
SPI workaround script for AC073TC1A display
This script tries different approaches to initialize the display
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, '/usr/local/dagr/src')

def run_command(cmd, description):
    """Run a command and return success status"""
    try:
        print(f"  {description}...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✅ {description} successful")
            return True
        else:
            print(f"  ❌ {description} failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ❌ {description} error: {e}")
        return False

def check_spi_status():
    """Check current SPI status"""
    print("\n🔧 Checking SPI status...")
    
    # Check device files
    spidev_exists = Path("/dev/spidev0.0").exists()
    print(f"  /dev/spidev0.0 exists: {spidev_exists}")
    
    # Check loaded modules
    try:
        result = subprocess.run(["lsmod"], capture_output=True, text=True)
        spi_modules = [line for line in result.stdout.split('\n') if 'spi' in line.lower()]
        print(f"  SPI modules loaded: {len(spi_modules)}")
        for module in spi_modules:
            print(f"    {module}")
    except:
        print("  Could not check loaded modules")
    
    return spidev_exists

def try_display_init():
    """Try to initialize the display"""
    print("\n🖼️  Testing display initialization...")
    
    try:
        from inky.auto import auto
        from PIL import Image, ImageDraw, ImageFont
        
        # Try auto-detection
        display = auto()
        print(f"  ✅ Auto-detection successful: {type(display).__name__}")
        print(f"     Display size: {display.width}x{display.height}")
        
        # Create test image
        img = Image.new('RGB', (display.width, display.height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "SPI Test", fill=(0, 0, 0))
        
        # Try to set image
        display.set_image(img)
        print("  ✅ set_image successful")
        
        # Try to show
        display.show()
        print("  ✅ show successful - display should update!")
        return True
        
    except SystemExit as e:
        if "pins we need are in use" in str(e):
            print(f"  ❌ GPIO conflict: {e}")
            return False
        else:
            print(f"  ❌ System exit: {e}")
            return False
    except Exception as e:
        print(f"  ❌ Display initialization failed: {e}")
        return False

def main():
    print("🚀 SPI Workaround Script for AC073TC1A Display")
    print("=" * 50)
    
    # Method 1: Try with current configuration
    print("\n📋 Method 1: Current configuration")
    check_spi_status()
    if try_display_init():
        print("✅ Success with current configuration!")
        return
    
    # Method 2: Reload SPI modules
    print("\n📋 Method 2: Reload SPI modules")
    run_command("sudo modprobe -r spi_bcm2835", "Unload spi_bcm2835")
    run_command("sudo modprobe -r spidev", "Unload spidev")
    time.sleep(1)
    run_command("sudo modprobe spidev", "Load spidev")
    run_command("sudo modprobe spi_bcm2835", "Load spi_bcm2835")
    time.sleep(1)
    
    check_spi_status()
    if try_display_init():
        print("✅ Success after module reload!")
        return
    
    # Method 3: Try with SPI disabled temporarily
    print("\n📋 Method 3: Temporary SPI disable")
    run_command("sudo modprobe -r spi_bcm2835", "Unload spi_bcm2835")
    run_command("sudo modprobe -r spidev", "Unload spidev")
    time.sleep(1)
    
    check_spi_status()
    if try_display_init():
        print("✅ Success with SPI disabled!")
        # Reload modules
        run_command("sudo modprobe spidev", "Reload spidev")
        run_command("sudo modprobe spi_bcm2835", "Reload spi_bcm2835")
        return
    
    # Restore modules even if failed
    run_command("sudo modprobe spidev", "Restore spidev")
    run_command("sudo modprobe spi_bcm2835", "Restore spi_bcm2835")
    
    print("\n❌ All methods failed. This display model may need special configuration.")
    print("Consider:")
    print("1. Different device tree overlays")
    print("2. Custom SPI configuration")
    print("3. Alternative display drivers")

if __name__ == "__main__":
    main()
