#!/bin/bash

# =============================================================================
# Script Name: install.sh
# Description: This script automates the installation of Dagr and creation of 
#              the Dagr service.
#
# Usage: ./install.sh
# =============================================================================

# Formatting stuff
bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)
green=$(tput setaf 2)

SOURCE=${BASH_SOURCE[0]}
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE
done
SCRIPT_DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )

DAGR_APP_NAME="dagr"
DAGR_INSTALL_ROOT="/usr/local/$DAGR_APP_NAME"
DAGR_SOURCE_DIR="$SCRIPT_DIR/../src"
DAGR_BIN_DIR="/usr/local/bin"
DAGR_VENV_DIR="$DAGR_INSTALL_ROOT/.venv"

DAGR_SERVICE_NAME="$DAGR_APP_NAME.service"
DAGR_SERVICE_SOURCE="$SCRIPT_DIR/$DAGR_SERVICE_NAME"
DAGR_SERVICE_TARGET="/etc/systemd/system/$DAGR_SERVICE_NAME"

DAGR_OS_DEPS_FILE="$SCRIPT_DIR/os-dependencies.txt"
DAGR_PY_DEPS_FILE="$SCRIPT_DIR/requirements.txt"

check_sudo_permissions() {
  # Ensure the script is run with sudo
  if [ "$EUID" -ne 0 ]; then
    error "Installation requires root privileges. Please run with sudo."
    exit 1
  fi
}


enable_system_interfaces() {
  info "Configuring system interfaces for e-ink displays"
  
  # Check if we're on a Raspberry Pi
  if [ ! -f "/boot/firmware/config.txt" ] && [ ! -f "/boot/config.txt" ]; then
    info "Not running on Raspberry Pi - skipping hardware interface configuration"
    return
  fi
  
  # Determine config file location
  CONFIG_FILE="/boot/firmware/config.txt"
  if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
  fi
  
  info "Using config file: $CONFIG_FILE"
  
  # Configure SPI for e-ink display communication
  # Enable SPI interface as required by Inky displays
  if grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
    success "SPI interface already enabled"
  elif grep -q "^#dtparam=spi=on" "$CONFIG_FILE"; then
    info "Enabling SPI interface for e-ink displays"
    sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG_FILE"
    success "SPI interface enabled"
  else
    echo "dtparam=spi=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
    success "SPI interface enabled"
  fi
  
  # Enable I2C interface for sensors and additional peripherals
  if grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE"; then
    success "I2C interface already enabled"
  elif grep -q "^#dtparam=i2c_arm=on" "$CONFIG_FILE"; then
    sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "$CONFIG_FILE"
    success "I2C interface enabled"
  else
    echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
    success "I2C interface enabled"
  fi
  
  # Add GPIO permissions for display access
  if ! grep -q "^gpio" /etc/group; then
    sudo groupadd gpio 2>/dev/null || true
  fi
  
  # Add current user to gpio group for display access
  if [ -n "$SUDO_USER" ]; then
    sudo usermod -a -G gpio,spi,i2c "$SUDO_USER" 2>/dev/null || true
    success "User permissions configured for display access"
  fi
}

spinner() {
  local pid=$!
  local delay=0.1
  local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  printf "  %s " "$1"
  while ps a | awk '{print $1}' | grep -q "${pid}"; do
    printf "\r  %s %c" "$1" "${spinstr:$i:1}"
    i=$(( (i+1) % ${#spinstr} ))
    sleep ${delay}
  done
  if [[ $? -eq 0 ]]; then
    printf "\r  %s ✓\n" "$1"
  else
    printf "\r  %s ✗\n" "$1"
  fi
}

success() {
  echo -e "  \e[32m✓\e[0m $1"
}

info() {
  echo -e "  \e[34mℹ\e[0m $1"
}

header() {
  echo -e "\n${bold}$1${normal}"
}

error() {
  echo -e "  \e[31m✗\e[0m $1" >&2
}

highlight() {
  echo -e "\e[36m$1\e[0m"
}


install_system_dependencies() {
  if [ -f "$DAGR_OS_DEPS_FILE" ]; then
    info "Installing system dependencies"
    sudo apt-get update > /dev/null &
    spinner "Updating package repositories"

    xargs -a "$DAGR_OS_DEPS_FILE" sudo apt-get install -y > /dev/null &
    spinner "Installing system packages"
  else
    error "System dependencies file not found: $DAGR_OS_DEPS_FILE"
    exit 1
  fi
}

optimize_system_performance() {
  info "Optimizing system performance"
  
  # Configure compressed RAM swap for better memory efficiency
  if systemctl is-enabled --quiet zramswap 2>/dev/null; then
    success "Memory compression already enabled"
  else
    echo -e "ALGO=zstd\nPERCENT=50" | sudo tee /etc/default/zramswap > /dev/null
    sudo systemctl enable --now zramswap 2>/dev/null
    success "Memory compression configured"
  fi

  # Enable memory management to prevent system freezes
  if systemctl is-enabled --quiet earlyoom 2>/dev/null; then
    success "Memory management already enabled"
  else
    sudo systemctl enable --now earlyoom 2>/dev/null
    success "Memory management enabled"
  fi
}

setup_python_environment(){
  info "Setting up Python environment"
  
  # Create virtual environment
  python3 -m venv "$DAGR_VENV_DIR"
  success "Virtual environment created"
  
  # Upgrade pip and core tools
  $DAGR_VENV_DIR/bin/python -m pip install --upgrade pip setuptools wheel > /dev/null &
  spinner "Upgrading pip and tools"

  # Install project dependencies
  if [ -f "$DAGR_PY_DEPS_FILE" ]; then
    $DAGR_VENV_DIR/bin/python -m pip install -r $DAGR_PY_DEPS_FILE > /dev/null &
    spinner "Installing Python packages"
  else
    info "No Python dependencies file found, skipping"
  fi
}

install_dagr_service() {
  info "Installing system service"
  if [ -f "$DAGR_SERVICE_SOURCE" ]; then
    cp "$DAGR_SERVICE_SOURCE" "$DAGR_SERVICE_TARGET"
    sudo systemctl daemon-reload
    sudo systemctl enable $DAGR_SERVICE_NAME
    success "Service installed and enabled"
  else
    error "Service file not found: $DAGR_SERVICE_SOURCE"
    exit 1
  fi
}

install_dagr_executable() {
  info "Installing executable"
  cp "$SCRIPT_DIR/$DAGR_APP_NAME" "$DAGR_BIN_DIR/"
  sudo chmod +x "$DAGR_BIN_DIR/$DAGR_APP_NAME"
  success "Executable installed to $DAGR_BIN_DIR"
}

setup_dagr_configuration() {
  DAGR_CONFIG_DIR="$DAGR_INSTALL_ROOT/config"
  
  info "Setting up configuration"
  
  # Create config directory if it doesn't exist
  mkdir -p "$DAGR_CONFIG_DIR"
  
  # Copy device configuration if it doesn't exist
  if [ -f "$SCRIPT_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/config.json" "$DAGR_CONFIG_DIR/"
    success "Configuration copied"
  else
    info "No configuration file found, will use defaults"
  fi
}

stop_dagr_service() {
    if /usr/bin/systemctl is-active --quiet $DAGR_SERVICE_NAME 2>/dev/null; then
      info "Stopping existing service"
      /usr/bin/systemctl stop $DAGR_SERVICE_NAME > /dev/null &
      spinner "Stopping service"
    else  
      info "No existing service running"
    fi
}

start_dagr_service() {
  info "Starting service"
  sudo systemctl start $DAGR_SERVICE_NAME
  success "Service started successfully"
}

setup_dagr_directories() {
  info "Setting up project directories"
  
  # Remove existing installation if present
  if [[ -d "$DAGR_INSTALL_ROOT" ]]; then
    rm -rf "$DAGR_INSTALL_ROOT" > /dev/null &
    spinner "Removing existing installation"
  fi

  # Create installation directory
  mkdir -p "$DAGR_INSTALL_ROOT"
  success "Project directory created"

  # Copy source code directly (no symlink to avoid systemd security issues)
  if [[ -d "$DAGR_SOURCE_DIR" ]]; then
    cp -r "$DAGR_SOURCE_DIR" "$DAGR_INSTALL_ROOT/"
    success "Source code copied to $DAGR_INSTALL_ROOT/src"
    
    # Set proper ownership and permissions
    chown -R root:root "$DAGR_INSTALL_ROOT/src"
    find "$DAGR_INSTALL_ROOT/src" -type f -name "*.py" -exec chmod 644 {} \;
    find "$DAGR_INSTALL_ROOT/src" -type f \( -name "dagr_*" -o -name "*.sh" \) -exec chmod 755 {} \;
    success "Permissions set correctly"
  else
    error "Source directory not found: $DAGR_SOURCE_DIR"
    exit 1
  fi
}

# Get system hostname
get_device_hostname() {
  echo "$(hostname)"
}

# Get system IP address
get_device_ip_address() {
  local ip_address=$(hostname -I | awk '{print $1}')
  echo "$ip_address"
}

# Get device MAC address
get_device_mac_address() {
  # Get MAC address of the first active network interface (excluding loopback)
  local mac_address=$(ip link show | grep -E "link/ether" | head -n1 | awk '{print $2}' | tr '[:lower:]' '[:upper:]')
  echo "$mac_address"
}

# Extract last 3 octets of MAC address for hostname suffix
get_mac_suffix() {
  local mac_address=$(get_device_mac_address)
  if [ -n "$mac_address" ]; then
    # Extract last 3 octets and remove colons (e.g., "AB:CD:EF" from "12:34:56:AB:CD:EF")
    echo "$mac_address" | cut -d':' -f4-6 | tr -d ':'
  else
    # Fallback to random 6-character hex string if MAC not found
    echo "$(openssl rand -hex 3 | tr '[:lower:]' '[:upper:]')"
  fi
}

# Set system hostname to dagr-XXX format
set_dagr_hostname() {
  local mac_suffix=$(get_mac_suffix)
  local new_hostname="dagr-$mac_suffix"
  
  info "Setting hostname to $new_hostname"
  
  # Set the hostname
  sudo hostnamectl set-hostname "$new_hostname"
  
  # Update /etc/hosts to include the new hostname
  sudo sed -i "s/127.0.1.1.*/127.0.1.1\t$new_hostname/" /etc/hosts
  
  # If the entry doesn't exist, add it
  if ! grep -q "127.0.1.1" /etc/hosts; then
    echo "127.0.1.1	$new_hostname" | sudo tee -a /etc/hosts > /dev/null
  fi
  
  success "Hostname set to $new_hostname"
}

complete_dagr_installation() {
  # Get system information
  local device_hostname=$(get_device_hostname)
  local device_ip_address=$(get_device_ip_address)
  local device_mac_address=$(get_device_mac_address)
  
  header "Installation Complete!"
  success "Dagr has been successfully installed"
  info "Device hostname: $(highlight "$device_hostname")"
  info "Device MAC address: $(highlight "$device_mac_address")"
  info "Device IP address: $(highlight "$device_ip_address")"
  info "A system reboot is required for hardware interface changes"
  info "After reboot, Dagr service will start automatically"

  echo
  read -p "Restart system now? [Y/n] " user_restart_input
  user_restart_input="${user_restart_input:-Y}"

  if [[ "${user_restart_input,,}" == "y" ]]; then
    info "Rebooting system..."
    sleep 2
    sudo reboot now
  else
    info "Please restart later with: sudo reboot"
    info "Manual service start: sudo systemctl start $DAGR_SERVICE_NAME"
    exit 0
  fi
}

# ============================================================================= 
# Main installation sequence
# =============================================================================

header "Dagr Installation"
info "Display management system for Raspberry Pi"
echo

check_sudo_permissions
stop_dagr_service
enable_system_interfaces
set_dagr_hostname
install_system_dependencies
optimize_system_performance
setup_dagr_directories
setup_python_environment
install_dagr_executable
setup_dagr_configuration
install_dagr_service
complete_dagr_installation
