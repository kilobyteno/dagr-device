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
except ImportError as e:
    print(f"Warning: Display dependencies not available: {e}")
    print("Running in simulation mode")

# Configuration
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/usr/local/dagr"))
SRC_DIR = Path(os.getenv("SRC_DIR", PROJECT_DIR / "src"))
CONFIG_DIR = Path(os.getenv("DAGR_CONFIG_DIR", PROJECT_DIR / "config"))
DEMO_DIR = SRC_DIR / "demo"
LOG_FILE = CONFIG_DIR / "display.log"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DIR.mkdir(parents=True, exist_ok=True)

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
        try:
            display_config = self.config.get("display", {})
            
            # Auto-detect and initialize display
            try:
                self.display = auto()
                logger.info(f"Auto-detected display: {type(self.display).__name__}")
            except Exception as e:
                logger.warning(f"No physical e-ink display found: {e}")
                logger.info("Running in simulation mode")
                self.display = None
            
            if self.display:
                # Configure display orientation
                orientation = display_config.get("orientation", "landscape")
                if orientation == "portrait":
                    self.display.set_rotation(90)
                else:
                    self.display.set_rotation(0)
                
                logger.info(f"Display configured: {self.display.width}x{self.display.height}")
                
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")
            self.display = None
    
    def get_demo_images(self) -> List[Path]:
        """Get list of demo images"""
        supported_formats = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
        images = []
        
        if DEMO_DIR.exists():
            for file_path in DEMO_DIR.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                    images.append(file_path)
        
        images.sort()  # Sort alphabetically
        logger.info(f"Found {len(images)} demo images: {[img.name for img in images]}")
        return images
    
    def prepare_image(self, image_path: Path) -> Optional[Image.Image]:
        """Prepare image for display"""
        try:
            # Load image
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
            
            # Create a new image with display dimensions and center the resized image
            display_image = Image.new('RGB', (display_width, display_height), (255, 255, 255))
            
            # Calculate position to center the image
            x = (display_width - new_width) // 2
            y = (display_height - new_height) // 2
            
            display_image.paste(image, (x, y))
            
            # Add timestamp and filename
            self.add_image_info(display_image, image_path.name)
            
            logger.info(f"Image prepared: {image_path.name} -> {display_width}x{display_height}")
            return display_image
            
        except Exception as e:
            logger.error(f"Failed to prepare image {image_path}: {e}")
            return None
    
    def add_image_info(self, image: Image.Image, filename: str):
        """Add timestamp and filename to image"""
        try:
            draw = ImageDraw.Draw(image)
            
            # Try to load a font, fall back to default if not available
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
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
            
            # Set image to display
            self.display.set_image(image)
            
            # Show on display
            self.display.show()
            logger.info("Image displayed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to display image: {e}")
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
            
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            except:
                font = ImageFont.load_default()
            
            message = "No demo images found"
            subtitle = f"Add images to: {DEMO_DIR}"
            
            # Center the text
            text_width = draw.textlength(message, font=font)
            x = (self.display.width - text_width) // 2
            y = self.display.height // 2 - 30
            
            draw.text((x, y), message, fill=(0, 0, 0), font=font)
            
            # Add subtitle
            try:
                small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
                small_font = font
            
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
        print(f"Demo Images: {len(images)} found")
        for i, img in enumerate(images):
            marker = "→" if i == self.current_image_index else " "
            print(f"  {marker} {img.name}")
        print(f"Rotation: {'Running' if self.running else 'Stopped'}")
        print(f"Interval: {self.rotation_interval} seconds (3 minutes)")
        print(f"Demo Directory: {DEMO_DIR}")
        print(f"Log File: {LOG_FILE}")

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
