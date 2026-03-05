# TODO: Optimize ip_listener.py for WiFi

## Steps:
1. [x] Read and analyze the current code
2. [x] Implement improved IP detection for WiFi compatibility
3. [x] Test the changes

## Changes made:
- Added `get_local_ips()` - Multi-method IP detection that queries all network interfaces
- Added `get_preferred_local_ip()` - Selects the best IP, skipping VPN ranges
- Added `is_valid_local_ip()` - Validates if an IP is a proper private address
- Added `is_same_subnet()` and `get_subnet_prefix()` - Improved subnet checking
- Updated `start_listener()` to use WiFi-optimized IP detection
- Added `SO_BROADCAST` socket option for better packet reception on WiFi
- Replaced hardcoded `10.95.` prefix checks with flexible validation
- Added detection of all network interfaces at startup for debugging

