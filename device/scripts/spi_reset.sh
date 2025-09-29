#!/bin/bash

# SPI Reset Script for DAGR
# Resolves GPIO conflicts with SPI interface for e-ink displays

LOG_FILE="/var/log/dagr-spi-reset.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

reset_spi() {
    log "Starting SPI reset for DAGR display..."
    
    # Stop any processes that might be using SPI
    pkill -f "spi" 2>/dev/null
    sleep 1
    
    # Reset SPI modules
    log "Removing SPI modules..."
    modprobe -r spi_bcm2835 2>/dev/null
    modprobe -r spi_bcm2835aux 2>/dev/null
    sleep 1
    
    log "Reloading SPI modules..."
    modprobe spi_bcm2835 2>/dev/null
    modprobe spi_bcm2835aux 2>/dev/null
    sleep 1
    
    # Check SPI devices
    if [ -e "/dev/spidev0.0" ] && [ -e "/dev/spidev0.1" ]; then
        log "SPI devices available: /dev/spidev0.0, /dev/spidev0.1"
    else
        log "WARNING: SPI devices not found"
    fi
    
    # Set proper permissions
    if [ -e "/dev/spidev0.0" ]; then
        chmod 666 /dev/spidev0.0 2>/dev/null
        chgrp spi /dev/spidev0.0 2>/dev/null
    fi
    
    if [ -e "/dev/spidev0.1" ]; then
        chmod 666 /dev/spidev0.1 2>/dev/null
        chgrp spi /dev/spidev0.1 2>/dev/null
    fi
    
    log "SPI reset completed"
}

case "$1" in
    start)
        reset_spi
        ;;
    stop)
        log "SPI reset stop requested (no action needed)"
        ;;
    restart)
        reset_spi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac

exit 0
