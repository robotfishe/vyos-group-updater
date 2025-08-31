import socket
import os
import glob
import ipaddress
import subprocess
from datetime import datetime, timedelta

#These options are probably fine for any VyOS system
DOMAINS_FILE = "/config/scripts/vpn_domains_dns.txt"
OUTPUT_DIR = "/config/groups"
MASTER_LIST_FILENAME = "vpn-addresses-v4-master.txt"
FILE_RETENTION_DAYS = 1

# Maximum gap to bridge when collapsing IP ranges. 0 means only adjacent IPs will be collapsed.
# 1 will automatically include e.g. 1.1.1.2 if DNS resuls include both 1.1.1.1 and 1.1.1.3
MAX_IP_RANGE_GAP = 1

#CHANGE THESE for your setup
DIG_PATH = "/usr/bin/dig"
DNS_SERVER = "10.4.1.2"

#This function is only needed when debugging
# LOG_FILE = "/var/log/dns_update.log" # Use an absolute path for the log file
# def log_message(message):
#     """
#     Writes a timestamped message to the specified log file.
#     """
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     log_entry = f"[{timestamp}] {message}\n"
#     print(log_entry, end="") # Also print to stdout for cron email/stdout redirection
#     try:
#         with open(LOG_FILE, 'a') as f:
#             f.write(log_entry)
#     except IOError as e:
#         # If logging fails, at least the message is printed to stdout
#         print(f"Error writing to log file {LOG_FILE}: {e}")


def get_domains_from_file(filepath):
    domains = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                domain = line.strip()
                if domain and not domain.startswith('#'):
                    domains.append(domain)
        print(f"echo Successfully read {len(domains)} domains from {filepath}")
    except FileNotFoundError:
        print(f"echo Error: The domains file {filepath} was not found.")
        print(f"echo Please create a file named {DOMAINS_FILE} with one domain per line.")
    except IOError as e:
        print(f"echo Error reading file {filepath}: {e}")

    return domains

def get_ips_for_domains(domain_list):
    all_ips = set()
    for domain in domain_list:
        try:
            result = subprocess.run(
                [DIG_PATH, "+short", "A", domain, f"@{DNS_SERVER}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            ip_addresses = [ip.strip() for ip in result.stdout.split('\n') if ip.strip()]
            for ip in ip_addresses:
                all_ips.add(ip)
            print(f"echo Successfully resolved {domain} IPv4 IPs via dig: {' '.join(ip_addresses)}")
        except subprocess.CalledProcessError as e:
            print(f"echo Error resolving {domain} IPv4 with dig: {e}")
        except subprocess.TimeoutExpired:
            print(f"echo Error: dig command for {domain} timed out.")

    return all_ips

def write_ips_to_file(ips, directory, filename):
    filepath = os.path.join(directory, filename)
    try:
        with open(filepath, 'w') as f:
            for ip in sorted(list(ips)):
                f.write(f"{ip}\n")
        print(f"echo Successfully wrote {len(ips)} IPs to {filepath}")
    except IOError as e:
            print(f"echo Error writing to file {filepath}: {e}")

def cleanup_old_files(directory, retention_days, prefix):
    now = datetime.now()
    cutoff_time = now - timedelta(days=retention_days)
    
    file_pattern = os.path.join(directory, f"{prefix}*")
    for filepath in glob.glob(file_pattern):
        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        print(f"echo DEBUG: Checking file {filepath} with modified time {file_mtime}")
        if file_mtime < cutoff_time:
            try:
                os.remove(filepath)
                print(f"echo Deleted old file: {filepath}")
            except OSError as e:
                print(f"echo Error deleting file {filepath}: {e}")

def get_vyos_config_items(config_path="/config/config.boot"):
    current_items = set()
    in_address_group = False
    
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if 'address-group VPN-ADDRESSES {' in line:
                    in_address_group = True
                elif in_address_group and line == '}':
                    in_address_group = False
                elif in_address_group and line.startswith('address '):
                    ip_item = line.split(' ')[1].strip('\'" ')
                    current_items.add(ip_item)
                    print(f"echo Found existing address/range {ip_item}")
    except IOError as e:
        print(f"echo Error reading VyOS config file {config_path}: {e}")
        print(f"echo Assuming no IPs are currently configured.")
    
    return current_items

def create_master_list_ips(directory, prefix):
    all_ips = set()
    
    file_pattern = os.path.join(directory, f"{prefix}*")
    for filepath in glob.glob(file_pattern):
        if os.path.basename(filepath) == MASTER_LIST_FILENAME:
            continue
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    ip = line.strip()
                    if ip:
                        all_ips.add(ip)
            print(f"echo Read IPs from {filepath}")
        except IOError as e:
            print(f"echo Error reading file {filepath}: {e}")
    
    return all_ips


def collapse_ips_to_ranges(ip_list, max_gap):
    if not ip_list:
        return []

    sorted_ips = sorted([ipaddress.IPv4Address(ip) for ip in ip_list])
    
    collapsed_list = []
    start_ip = sorted_ips[0]
    end_ip = sorted_ips[0]

    for i in range(1, len(sorted_ips)):
        current_ip = sorted_ips[i]
        if int(current_ip) - int(end_ip) <= max_gap + 1:
            end_ip = current_ip
        else:
            if start_ip == end_ip:
                collapsed_list.append(str(start_ip))
            else:
                collapsed_list.append(f"{start_ip}-{end_ip}")
            
            start_ip = current_ip
            end_ip = current_ip

    if start_ip == end_ip:
        collapsed_list.append(str(start_ip))
    else:
        collapsed_list.append(f"{start_ip}-{end_ip}")

    return collapsed_list


def generate_vyos_commands_diff(new_ips_flat, vyos_config_items):
    new_ranges = collapse_ips_to_ranges(list(new_ips_flat), MAX_IP_RANGE_GAP)
    
    items_to_add = []
    items_to_delete = []

    for old_item in vyos_config_items:
        if old_item not in new_ranges:
            items_to_delete.append(old_item)
            
    for new_range in new_ranges:
        if new_range not in vyos_config_items:
            items_to_add.append(new_range)
    
    if items_to_delete:
        print(f"echo Deleting {len(items_to_delete)} old IP ranges from address-group...")
        for item in sorted(items_to_delete):
            print(f"delete firewall group address-group VPN-ADDRESSES address {item}")
            print(f"echo   - deleted {item}")

    if items_to_add:
        print(f"echo Adding {len(items_to_add)} new IP ranges to address-group...")
        for item in sorted(items_to_add):
            print(f"set firewall group address-group VPN-ADDRESSES address {item}")
            print(f"echo   - added {item}")
            

def main():
    print(f"echo Starting IP update script...")

    domains_to_resolve = get_domains_from_file(DOMAINS_FILE)

    current_dns_ips = get_ips_for_domains(domains_to_resolve)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    current_filename = f"vpn-addresses-v4-{timestamp}.txt"
    write_ips_to_file(current_dns_ips, OUTPUT_DIR, current_filename)

    new_master_ips = create_master_list_ips(OUTPUT_DIR, "vpn-addresses-v4")

    vyos_config_items = get_vyos_config_items()

    generate_vyos_commands_diff(new_master_ips, vyos_config_items)

    master_filepath = os.path.join(OUTPUT_DIR, MASTER_LIST_FILENAME)
    write_ips_to_file(new_master_ips, OUTPUT_DIR, MASTER_LIST_FILENAME)

    cleanup_old_files(OUTPUT_DIR, FILE_RETENTION_DAYS, "vpn-addresses-v4")

    print(f"echo Script execution finished.")


if __name__ == "__main__":
    main()
