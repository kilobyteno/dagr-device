#!/usr/bin/env python3
"""
Dagr Display Manager
Manages e-ink display content and rotation
"""

import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from typing import List, Optional
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    from inky.auto import auto
    import numpy as np
    INKY_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Inky display dependencies not available: {e}")
    print("Running in simulation mode")
    INKY_AVAILABLE = False

# Configuration
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/usr/local/dagr"))
SRC_DIR = Path(os.getenv("SRC_DIR", PROJECT_DIR / "src"))
CONFIG_DIR = Path(os.getenv("DAGR_CONFIG_DIR", PROJECT_DIR / "config"))
DEMO_DIR = SRC_DIR / "demo"
LOG_FILE = CONFIG_DIR / "display.log"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
# Note: Don't auto-create DEMO_DIR as it should come with demo images from installation

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("display_manager")

class DisplayManager:
    """Manages e-ink display operations"""
    
    def __init__(self):
        self.config = self.load_config()
        self.display = None
        self.current_image_index = 0
        self.rotation_interval = 180  # 3 minutes in seconds
        self.running = False
        self.rotation_thread = None
        
        # Initialize display
        self.initialize_display()
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        config_file = CONFIG_DIR / "config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                logger.info("Configuration loaded successfully")
                return config
            except Exception as e:
                logger.warning(f"Could not load config file: {e}")
        
        # Default configuration
        return {
            "display": {
                "type": "eink",
                "orientation": "landscape",
                "invert_colors": False,
                "rotation": 0,
                "auto_refresh": True
            }
        }
    
    def initialize_display(self):
        """Initialize the e-ink display"""
        display_config = self.config.get("display", {})
        
        # Check for required device files first
        device_files_to_check = [
            "/dev/spidev0.0",
            "/dev/spidev0.1", 
            "/dev/gpiomem",
            "/sys/class/gpio"
        ]
        
        missing_files = []
        for device_file in device_files_to_check:
            if Path(device_file).exists():
                logger.info(f"Device file exists: {device_file}")
            else:
                logger.warning(f"Device file missing: {device_file}")
                missing_files.append(device_file)
        
        if missing_files:
            logger.warning(f"Missing device files: {missing_files}")
            logger.info("This might indicate SPI interface is not enabled")
        
        # Try Inky display detection
        if INKY_AVAILABLE:
            try:
                logger.info("Attempting Inky display auto-detection...")
                self.display = auto()
                logger.info(f"✅ Inky display detected: {type(self.display).__name__}")
                logger.info(f"Display model: {getattr(self.display, '_model', 'Unknown')}")
                logger.info(f"Display resolution: {self.display.width}x{self.display.height}")
                logger.info(f"Display color mode: {self.display.colour}")
                self._configure_display_orientation()
                return
            except SystemExit as e:
                if "pins we need are in use" in str(e):
                    logger.error(f"GPIO pin conflict detected: {e}")
                    logger.error("This indicates SPI interface configuration issues.")
                    logger.info("Attempting GPIO conflict resolution...")
                    
                    # Try to resolve conflict and retry once
                    if self._resolve_display_gpio_conflict():
                        try:
                            logger.info("Retrying Inky display detection after conflict resolution...")
                            self.display = auto()
                            logger.info(f"✅ Inky display detected after resolution: {type(self.display).__name__}")
                            self._configure_display_orientation()
                            return
                        except Exception as retry_e:
                            logger.warning(f"Inky display still failed after conflict resolution: {retry_e}")
                    
                    logger.info("Running in simulation mode due to GPIO conflict")
                    self.display = None
                    return
                else:
                    logger.warning(f"System exit during Inky display detection: {e}")
            except Exception as e:
                logger.warning(f"Inky display detection failed: {e}")
        
        # No display detected - run in simulation mode
        logger.warning("No physical Inky display detected")
        logger.info("Running in simulation mode")
        self.display = None
    
    
    def _configure_display_orientation(self):
        """Configure display orientation after successful initialization"""
        if not self.display:
            return
            
        display_config = self.config.get("display", {})
        orientation = display_config.get("orientation", "landscape")
        
        try:
            if orientation == "portrait":
                if hasattr(self.display, 'set_rotation'):
                    self.display.set_rotation(90)
                elif hasattr(self.display, 'rotation'):
                    self.display.rotation = 90
            else:
                if hasattr(self.display, 'set_rotation'):
                    self.display.set_rotation(0)
                elif hasattr(self.display, 'rotation'):
                    self.display.rotation = 0
            logger.info(f"Display orientation set to: {orientation}")
        except Exception as e:
            logger.warning(f"Could not set display orientation: {e}")
        
        logger.info(f"Display configured: {self.display.width}x{self.display.height}")
    
    def _resolve_display_gpio_conflict(self) -> bool:
        """Resolve GPIO conflicts during display operations"""
        try:
            import subprocess
            import time
            
            logger.info("Attempting to resolve GPIO conflict for display update...")
            
            # Method 1: Reset SPI interface completely
            try:
                logger.info("Resetting SPI interface...")
                
                # Stop any processes that might be using SPI
                subprocess.run(["sudo", "pkill", "-f", "spi"], capture_output=True, timeout=5)
                time.sleep(0.5)
                
                # Unbind SPI devices
                spi_devices = ["/sys/bus/spi/drivers/spi-bcm2835/20204000.spi"]
                for device in spi_devices:
                    try:
                        if Path(device).exists():
                            with open(f"{device}/unbind", "w") as f:
                                f.write("20204000.spi")
                            logger.debug("Unbound SPI device")
                            time.sleep(0.2)
                    except Exception:
                        pass
                
                # Remove and reload SPI modules
                spi_modules = ["spi_bcm2835", "spi_bcm2835aux"]
                for module in spi_modules:
                    try:
                        subprocess.run(["sudo", "modprobe", "-r", module], 
                                     capture_output=True, timeout=5)
                        logger.debug(f"Removed module {module}")
                    except Exception:
                        pass
                
                time.sleep(0.5)
                
                # Reload SPI modules
                for module in spi_modules:
                    try:
                        subprocess.run(["sudo", "modprobe", module], 
                                     capture_output=True, timeout=5)
                        logger.debug(f"Loaded module {module}")
                    except Exception:
                        pass
                
                time.sleep(1.0)
                
                # Rebind SPI devices
                for device in spi_devices:
                    try:
                        if Path(device.replace("/unbind", "/bind")).exists():
                            with open(f"{device.replace('/unbind', '/bind')}", "w") as f:
                                f.write("20204000.spi")
                            logger.debug("Rebound SPI device")
                            time.sleep(0.2)
                    except Exception:
                        pass
                
                logger.info("SPI interface reset completed")
                return True
                
            except subprocess.TimeoutExpired:
                logger.warning("SPI reset timed out")
                return False
            except Exception as spi_e:
                logger.warning(f"SPI reset failed: {spi_e}")
                
                # Fallback: Try simple GPIO release
                logger.info("Trying fallback GPIO release...")
                gpio_pins_to_release = [8, 7, 10, 11, 25]  # Common SPI and display pins
                for pin in gpio_pins_to_release:
                    try:
                        # Try to unexport the pin if it's exported
                        if Path(f"/sys/class/gpio/gpio{pin}").exists():
                            with open(f"/sys/class/gpio/unexport", "w") as f:
                                f.write(str(pin))
                            logger.debug(f"Released GPIO pin {pin}")
                            time.sleep(0.1)
                    except Exception:
                        pass  # Pin might not be exported, which is fine
                
                time.sleep(0.5)
                return True
                
        except Exception as e:
            logger.error(f"GPIO conflict resolution failed: {e}")
            return False
    
    def create_demo_placeholder(self):
        """Create a placeholder demo image if no images exist"""
        try:
            DEMO_DIR.mkdir(parents=True, exist_ok=True)
            
            # Create a simple placeholder image
            placeholder_path = DEMO_DIR / "placeholder.png"
            if not placeholder_path.exists():
                # Create a placeholder image with correct display dimensions
                from PIL import Image, ImageDraw, ImageFont
                
                # Use display dimensions if available, otherwise use a reasonable default
                width, height = (800, 480)  # Default for detected display
                if self.display:
                    width, height = self.display.width, self.display.height
                
                img = Image.new('RGB', (width, height), color=(240, 240, 240))
                draw = ImageDraw.Draw(img)
                
                # Try to get a font for the text
                font = None
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/TTF/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
                ]
                
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, 24)
                        break
                    except (OSError, IOError):
                        continue
                
                if font is None:
                    font = ImageFont.load_default()
                
                # Add text to the placeholder
                text = "Dagr Demo Image"
                subtitle = "Add your images to:"
                path_text = str(DEMO_DIR)
                
                # Center the main text
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                x = (width - text_width) // 2
                y = height // 2 - 60
                
                draw.text((x, y), text, fill=(60, 60, 60), font=font)
                
                # Add subtitle and path
                small_font = None
                for font_path in font_paths:
                    try:
                        small_font = ImageFont.truetype(font_path, 14)
                        break
                    except (OSError, IOError):
                        continue
                
                if small_font is None:
                    small_font = font
                
                subtitle_bbox = draw.textbbox((0, 0), subtitle, font=small_font)
                subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
                x = (width - subtitle_width) // 2
                y = height // 2 - 20
                draw.text((x, y), subtitle, fill=(100, 100, 100), font=small_font)
                
                path_bbox = draw.textbbox((0, 0), path_text, font=small_font)
                path_width = path_bbox[2] - path_bbox[0]
                x = (width - path_width) // 2
                y = height // 2 + 10
                draw.text((x, y), path_text, fill=(100, 100, 100), font=small_font)
                
                # Save the placeholder image
                img.save(placeholder_path, 'PNG')
                logger.info(f"Created placeholder demo image: {placeholder_path}")
                
        except Exception as e:
            logger.error(f"Failed to create demo placeholder: {e}")
    
    def get_demo_images(self) -> List[Path]:
        """Get list of demo images"""
        supported_formats = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
        images = []
        
        logger.info(f"Looking for demo images in: {DEMO_DIR}")
        logger.info(f"Demo directory exists: {DEMO_DIR.exists()}")
        
        if DEMO_DIR.exists():
            logger.info(f"Demo directory contents: {list(DEMO_DIR.iterdir())}")
            for file_path in DEMO_DIR.iterdir():
                logger.info(f"Checking file: {file_path} (is_file: {file_path.is_file()}, suffix: {file_path.suffix.lower()})")
                if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                    images.append(file_path)
        else:
            logger.error(f"Demo directory does not exist: {DEMO_DIR}")
            logger.info(f"Parent directory exists: {DEMO_DIR.parent.exists()}")
            if DEMO_DIR.parent.exists():
                logger.info(f"Parent directory contents: {list(DEMO_DIR.parent.iterdir())}")
            
            # Try to create demo directory with a placeholder image
            try:
                self.create_demo_placeholder()
                # Retry getting images after creating placeholder
                if DEMO_DIR.exists():
                    for file_path in DEMO_DIR.iterdir():
                        if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                            images.append(file_path)
            except Exception as e:
                logger.warning(f"Could not create demo placeholder: {e}")
        
        images.sort()  # Sort alphabetically
        logger.info(f"Found {len(images)} demo images: {[img.name for img in images]}")
        return images
    
    def prepare_image(self, image_path: Path) -> Optional[Image.Image]:
        """Prepare image for display"""
        try:
            # Check if image file exists
            if not image_path.exists():
                logger.error(f"Image file does not exist: {image_path}")
                return None
            
            # Load image
            logger.info(f"Loading image: {image_path}")
            image = Image.open(image_path)
            logger.info(f"Loaded image: {image_path.name} ({image.size})")
            
            if not self.display:
                # Simulation mode - just return resized image
                return image.resize((400, 300))
            
            # Get display dimensions
            display_width = self.display.width
            display_height = self.display.height
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Calculate aspect ratios
            img_aspect = image.width / image.height
            display_aspect = display_width / display_height
            
            # Resize to fit display while maintaining aspect ratio
            if img_aspect > display_aspect:
                # Image is wider than display
                new_width = display_width
                new_height = int(display_width / img_aspect)
            else:
                # Image is taller than display
                new_height = display_height
                new_width = int(display_height * img_aspect)
            
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create a new image with exact display dimensions and center the resized image
            display_image = Image.new('RGB', (display_width, display_height), (255, 255, 255))
            
            # Calculate position to center the image
            x = (display_width - new_width) // 2
            y = (display_height - new_height) // 2
            
            display_image.paste(image, (x, y))
            
            # Ensure the final image is exactly the right size
            if display_image.size != (display_width, display_height):
                logger.warning(f"Image size mismatch: {display_image.size} != ({display_width}, {display_height})")
                display_image = display_image.resize((display_width, display_height), Image.Resampling.LANCZOS)
            
            # Add timestamp and filename
            self.add_image_info(display_image, image_path.name)
            
            logger.info(f"Image prepared: {image_path.name} -> {display_width}x{display_height}")
            return display_image
            
        except Exception as e:
            logger.error(f"Failed to prepare image {image_path}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def add_image_info(self, image: Image.Image, filename: str):
        """Add timestamp and filename to image"""
        try:
            draw = ImageDraw.Draw(image)
            
            # Try to load a font, fall back to default if not available
            font = None
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/System/Library/Fonts/Arial.ttf",  # macOS fallback
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            ]
            
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, 12)
                    break
                except (OSError, IOError):
                    continue
            
            if font is None:
                font = ImageFont.load_default()
            
            # Add timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Add info at bottom of image
            text_y = image.height - 25
            draw.text((5, text_y), f"{filename} | {timestamp}", fill=(0, 0, 0), font=font)
            
        except Exception as e:
            logger.warning(f"Could not add image info: {e}")
    
    def display_image(self, image: Image.Image):
        """Display image on e-ink display"""
        try:
            if not self.display:
                logger.info("Simulation mode: Would display image")
                return True
            
            display_type = type(self.display).__name__
            logger.info(f"Setting image on display (type: {display_type})")
            
            # Inky displays use set_image/show pattern
            try:
                self.display.set_image(image)
                logger.info("Image set on display successfully")
            except Exception as e:
                logger.error(f"Failed to set image on display: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            # Show on display with GPIO conflict handling
            try:
                logger.info("Calling display.show()")
                self.display.show()
                logger.info("Image displayed successfully")
            except SystemExit as e:
                if "pins we need are in use" in str(e):
                    logger.warning(f"GPIO conflict during display.show(): {e}")
                    logger.info("Attempting to resolve GPIO conflict for display update...")
                    
                    # Try to resolve the conflict and retry
                    success = self._resolve_display_gpio_conflict()
                    if success:
                        try:
                            logger.info("Retrying display.show() after conflict resolution...")
                            self.display.show()
                            logger.info("Image displayed successfully after conflict resolution")
                        except Exception as retry_e:
                            logger.error(f"Display update failed even after conflict resolution: {retry_e}")
                            raise
                    else:
                        logger.error("Could not resolve GPIO conflict for display update")
                        raise
                else:
                    logger.error(f"System exit during display.show(): {e}")
                    raise
            except Exception as e:
                logger.error(f"Failed to show image on display: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to display image: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    
    def show_next_image(self):
        """Show the next image in rotation"""
        images = self.get_demo_images()
        
        if not images:
            logger.warning("No demo images found")
            self.show_no_images_message()
            return
        
        # Get current image
        image_path = images[self.current_image_index]
        logger.info(f"Showing image {self.current_image_index + 1}/{len(images)}: {image_path.name}")
        
        # Prepare and display image
        prepared_image = self.prepare_image(image_path)
        if prepared_image:
            self.display_image(prepared_image)
        
        # Move to next image
        self.current_image_index = (self.current_image_index + 1) % len(images)
    
    def show_no_images_message(self):
        """Show message when no images are available"""
        try:
            if not self.display:
                logger.info("Simulation mode: Would show 'No images' message")
                return
            
            # Create a simple message image
            image = Image.new('RGB', (self.display.width, self.display.height), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            
            # Try to load a bold font, fall back to regular or default
            font = None
            bold_font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Regular as fallback
                "/System/Library/Fonts/Arial.ttf"  # macOS fallback
            ]
            
            for font_path in bold_font_paths:
                try:
                    font = ImageFont.truetype(font_path, 24)
                    break
                except (OSError, IOError):
                    continue
            
            if font is None:
                font = ImageFont.load_default()
            
            message = "No demo images found"
            subtitle = f"Add images to: {DEMO_DIR}"
            
            # Center the text
            text_width = draw.textlength(message, font=font)
            x = (self.display.width - text_width) // 2
            y = self.display.height // 2 - 30
            
            draw.text((x, y), message, fill=(0, 0, 0), font=font)
            
            # Add subtitle with smaller font
            small_font = None
            small_font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/System/Library/Fonts/Arial.ttf"
            ]
            
            for font_path in small_font_paths:
                try:
                    small_font = ImageFont.truetype(font_path, 12)
                    break
                except (OSError, IOError):
                    continue
            
            if small_font is None:
                small_font = font  # Use the main font as fallback
            
            subtitle_width = draw.textlength(subtitle, font=small_font)
            x = (self.display.width - subtitle_width) // 2
            y += 40
            
            draw.text((x, y), subtitle, fill=(100, 100, 100), font=small_font)
            
            self.display_image(image)
            
        except Exception as e:
            logger.error(f"Failed to show no images message: {e}")
    
    def rotation_worker(self):
        """Worker thread for image rotation"""
        logger.info(f"Starting image rotation (interval: {self.rotation_interval}s)")
        
        while self.running:
            try:
                self.show_next_image()
                
                # Wait for next rotation
                for _ in range(self.rotation_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in rotation worker: {e}")
                time.sleep(10)  # Wait before retrying
    
    def start_rotation(self):
        """Start automatic image rotation"""
        if self.running:
            logger.warning("Rotation already running")
            return
        
        self.running = True
        self.rotation_thread = threading.Thread(target=self.rotation_worker, daemon=True)
        self.rotation_thread.start()
        logger.info("Image rotation started")
    
    def stop_rotation(self):
        """Stop automatic image rotation"""
        if not self.running:
            return
        
        logger.info("Stopping image rotation")
        self.running = False
        
        if self.rotation_thread:
            self.rotation_thread.join(timeout=5)
        
        logger.info("Image rotation stopped")
    
    def display_status(self):
        """Display current status"""
        images = self.get_demo_images()
        print(f"\n🖥️  Dagr Display Manager Status")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Display: {'Connected' if self.display else 'Simulation Mode'}")
        if self.display:
            print(f"Resolution: {self.display.width}x{self.display.height}")
            print(f"Display Type: {type(self.display).__name__}")
            print(f"Color Mode: {getattr(self.display, 'colour', 'Unknown')}")
        print(f"Demo Images: {len(images)} found")
        for i, img in enumerate(images):
            marker = "→" if i == self.current_image_index else " "
            print(f"  {marker} {img.name}")
        print(f"Rotation: {'Running' if self.running else 'Stopped'}")
        print(f"Interval: {self.rotation_interval} seconds (3 minutes)")
        print(f"Demo Directory: {DEMO_DIR}")
        print(f"Log File: {LOG_FILE}")
        
    def get_status_dict(self):
        """Get status as dictionary for API responses"""
        images = self.get_demo_images()
        return {
            "display_connected": self.display is not None,
            "display_type": type(self.display).__name__ if self.display else "None",
            "display_resolution": f"{self.display.width}x{self.display.height}" if self.display else "Unknown",
            "color_mode": getattr(self.display, 'colour', 'Unknown') if self.display else "Unknown",
            "rotation_running": self.running,
            "rotation_interval": self.rotation_interval,
            "current_image_index": self.current_image_index,
            "total_images": len(images),
            "images": [img.name for img in images],
            "demo_directory": str(DEMO_DIR)
        }

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dagr Display Manager")
    parser.add_argument("--start", action="store_true", help="Start image rotation")
    parser.add_argument("--stop", action="store_true", help="Stop image rotation")
    parser.add_argument("--next", action="store_true", help="Show next image")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    
    args = parser.parse_args()
    
    # Create display manager
    display_manager = DisplayManager()
    
    try:
        if args.status or not any(vars(args).values()):
            display_manager.display_status()
        
        if args.next:
            display_manager.show_next_image()
        
        if args.start or args.daemon:
            display_manager.start_rotation()
            
            if args.daemon:
                logger.info("Running as daemon - press Ctrl+C to stop")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal")
                finally:
                    display_manager.stop_rotation()
        
        if args.stop:
            display_manager.stop_rotation()
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        display_manager.stop_rotation()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
