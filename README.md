# Dagr Device

## Hardware Compatibility

### Supported Displays
- **Pimoroni Inky Displays**
  - Inky Impression (13.3", 7.3", 5.7", 4.0")
  - Inky wHAT (4.2")
  - Auto-detection and configuration

## Installation

1. Clone the repository:
```bash
git clone https://github.com/kilobyteno/dagr-device.git && cd dagr-device
```

2. Run the installation script with sudo and follow the instructions:
```bash
sudo bash device/install.sh
```
Want to know what is going on? Run the install command with the `--verbose` option.

## Configuration

### Display Configuration

Edit `/usr/local/dagr/config/config.json`:

```json
{
  "display": {
    "type": "eink",
    "orientation": "landscape",
    "auto_refresh": true
  }
}
```

## License

Check the [licsense](LICENSE) file for details.
