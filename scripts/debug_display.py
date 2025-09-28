#!/usr/bin/env python3
"""
Debug script to test display functionality with correct dimensions
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, '/usr/local/dagr/src')

try:
    from inky.auto import auto
    from PIL import Image, ImageDraw, ImageFont
    print("✅ Imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

def test_auto_detection():
    """Test auto-detection"""
    print("\n🔍 Testing auto-detection...")
    try:
        display = auto()
        print(f"✅ Auto-detection successful: {type(display).__name__}")
        print(f"   Display size: {display.width}x{display.height}")
        print(f"   Display color: {display.colour}")
        return display
    except Exception as e:
        print(f"❌ Auto-detection failed: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return None

def test_image_creation(display):
    """Test creating a simple image with correct dimensions"""
    print("\n🖼️  Testing image creation...")
    if not display:
        print("❌ Cannot create image - no display detected")
        return None
    
    try:
        # Use exact display dimensions
        width, height = display.width, display.height
        print(f"   Creating image with dimensions: {width}x{height}")
        
        img = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Add some text centered on the image
        text = "Test Image"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        except:
            font = ImageFont.load_default()
        
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
        
        print(f"   ✅ Image creation successful: {img.size}")
        return img
    except Exception as e:
        print(f"❌ Image creation failed: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return None

def test_display_operations(display, image):
    """Test display operations step by step"""
    if not display or not image:
        print("❌ Cannot test display operations - missing display or image")
        return
    
    print(f"\n📺 Testing display operations...")
    
    # Verify image dimensions match display
    if image.size != (display.width, display.height):
        print(f"   ❌ Image size mismatch: {image.size} != ({display.width}, {display.height})")
        return
    else:
        print(f"   ✅ Image dimensions match display: {image.size}")
    
    # Test set_image
    try:
        print("   Testing set_image...")
        display.set_image(image)
        print("   ✅ set_image successful")
    except Exception as e:
        print(f"   ❌ set_image failed: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return
    
    # Test show with GPIO conflict handling
    try:
        print("   Testing show...")
        display.show()
        print("   ✅ show successful - image should now be on display!")
    except SystemExit as e:
        if "pins we need are in use" in str(e):
            print(f"   ⚠️  GPIO conflict detected: {e}")
            print("   🔧 Attempting to resolve GPIO conflict...")
            
            # Try to resolve the conflict
            success = resolve_gpio_conflict()
            if success:
                try:
                    print("   🔄 Retrying display.show() after conflict resolution...")
                    display.show()
                    print("   ✅ show successful after conflict resolution - image should now be on display!")
                except Exception as retry_e:
                    print(f"   ❌ show failed even after conflict resolution: {retry_e}")
                    import traceback
                    print(f"   Traceback: {traceback.format_exc()}")
                    return
            else:
                print("   ❌ Could not resolve GPIO conflict")
                return
        else:
            print(f"   ❌ System exit during show: {e}")
            return
    except Exception as e:
        print(f"   ❌ show failed: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return

def resolve_gpio_conflict():
    """Resolve GPIO conflicts during display operations"""
    try:
        import subprocess
        import time
        
        print("   🔧 Attempting GPIO conflict resolution...")
        
        # Method 1: Try to release GPIO pins that might be in use
        gpio_pins_to_release = [8, 7, 10, 11, 25]  # Common SPI and display pins
        for pin in gpio_pins_to_release:
            try:
                # Try to unexport the pin if it's exported
                with open(f"/sys/class/gpio/unexport", "w") as f:
                    f.write(str(pin))
                print(f"   🔓 Released GPIO pin {pin}")
            except:
                pass  # Pin might not be exported, which is fine
        
        time.sleep(0.2)
        
        # Method 2: Try to temporarily disable and re-enable SPI
        try:
            print("   🔄 Temporarily managing SPI modules...")
            
            # Disable SPI briefly
            result = subprocess.run(
                ["sudo", "modprobe", "-r", "spi_bcm2835"], 
                capture_output=True, text=True, timeout=5
            )
            
            time.sleep(0.1)
            
            # Re-enable SPI
            subprocess.run(
                ["sudo", "modprobe", "spi_bcm2835"], 
                capture_output=True, text=True, timeout=5
            )
            
            time.sleep(0.2)
            print("   ✅ GPIO conflict resolution completed")
            return True
            
        except subprocess.TimeoutExpired:
            print("   ⚠️  SPI module management timed out")
            return False
        except Exception as spi_e:
            print(f"   ⚠️  SPI module management failed: {spi_e}")
            return False
            
    except Exception as e:
        print(f"   ❌ GPIO conflict resolution failed: {e}")
        return False

def check_device_files():
    """Check required device files"""
    print("\n🔧 Checking device files...")
    
    device_files = [
        "/dev/spidev0.0",
        "/dev/spidev0.1",
        "/dev/gpiomem",
        "/sys/class/gpio"
    ]
    
    for device_file in device_files:
        if Path(device_file).exists():
            print(f"   ✅ {device_file}")
        else:
            print(f"   ❌ {device_file} (missing)")

def main():
    print("🚀 Dagr Display Debug Script (Fixed Dimensions)")
    print("=" * 50)
    
    # Check device files first
    check_device_files()
    
    # Test auto-detection
    display = test_auto_detection()
    
    # Test image creation with correct dimensions
    image = test_image_creation(display)
    
    # Test display operations
    test_display_operations(display, image)
    
    print("\n✨ Debug complete!")

if __name__ == "__main__":
    main()
