import os
import glob
import ipaddress
import subprocess
from datetime import datetime, timedelta

#These options are probably fine for any VyOS system
DOMAINS_FILE = "/config/scripts/vpn_domains_dns.txt"
OUTPUT_DIR = "/config/groups"
MASTER_LIST_FILENAME = "vpn-addresses-v6-master.txt"
FILE_RETENTION_DAYS = 1

# How large a range to assume should be included along with the individual address returned by DNS.
# /64 is the default. /56 or even /48 is probably safe.
IPV6_PREFIX_LENGTH = 64

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

def normalize_ipv6_range_string(range_str):
    if '-' in range_str:
        start_str, end_str = range_str.split('-')
        try:
            start_ip = ipaddress.IPv6Address(start_str)
            end_ip = ipaddress.IPv6Address(end_str)
            return f"{str(start_ip)}-{str(end_ip)}"
        except (ipaddress.AddressValueError, ValueError):
            return range_str
    else:
        try:
            return str(ipaddress.IPv6Address(range_str))
        except (ipaddress.AddressValueError, ValueError):
            return range_str

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
                [DIG_PATH, "+short", "AAAA", domain, f"@{DNS_SERVER}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            ip_addresses = [ip.strip() for ip in result.stdout.split('\n') if ip.strip()]
            for ip in ip_addresses:
                all_ips.add(ip)
            print(f"echo Successfully resolved {domain} IPv6 IPs via dig: {' '.join(ip_addresses)}")
        except subprocess.CalledProcessError as e:
            print(f"echo Error resolving {domain} IPv6 with dig: {e}")
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

    print(f"echo DEBUG: Current time is {now}")
    print(f"echo DEBUG: Cutoff time for deletion is {cutoff_time}")

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
                if 'ipv6-address-group VPN-ADDRESSES-v6 {' in line:
                    in_address_group = True
                elif in_address_group and line == '}':
                    in_address_group = False
                elif in_address_group and line.startswith('address '):
                    ip_item = line.split(' ')[1].strip('\'" ')
                    current_items.add(ip_item)
                    print(f"echo Found existing IPv6 address/prefix {ip_item}")
    except IOError as e:
        print(f"echo Error reading VyOS config file {config_path}: {e}")
        print(f"echo Assuming no IPv6 IPs are currently configured.")

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
            print(f"echo Read IPv6 IPs from {filepath}")
        except IOError as e:
            print(f"echo Error reading file {filepath}: {e}")

    return all_ips

def get_subnets_for_ips(ip_list, prefix_len):
    subnets = set()
    for ip in ip_list:
        try:
            subnet = ipaddress.IPv6Network(f'{ip}/{prefix_len}', strict=False)
            subnets.add(str(subnet))
        except (ipaddress.AddressValueError, ValueError) as e:
            print(f"echo Warning: Invalid IPv6 address found: {ip} - {e}")
            continue
    return subnets

def convert_subnets_to_ranges(subnets):
    ranges = []
    for subnet_str in subnets:
        try:
            subnet = ipaddress.IPv6Network(subnet_str, strict=False)
            start_ip = str(subnet.network_address)
            end_ip = str(subnet.broadcast_address)
            if start_ip.endswith('::'):
                start_ip = start_ip + '0'
            ranges.append(f"{start_ip}-{end_ip}")
        except ValueError as e:
            print(f"echo Warning: Invalid subnet found: {subnet_str} - {e}")
            continue
    return ranges


def generate_vyos_commands_diff(new_ranges, vyos_config_items):
    print(f"echo ")
    print(f"echo Generating VyOS commands...")

    items_to_add = set(new_ranges) - vyos_config_items
    items_to_delete = vyos_config_items - set(new_ranges)

    if items_to_delete:
        print(f"echo Deleting {len(items_to_delete)} old IPv6 prefixes from address-group...")
        for item in sorted(list(items_to_delete)):
            print(f"delete firewall group ipv6-address-group VPN-ADDRESSES-v6 address {item}")
            print(f"echo   - deleted {item}")

    if items_to_add:
        print(f"echo Adding {len(items_to_add)} new IPv6 prefixes to address-group...")
        for item in sorted(list(items_to_add)):
            print(f"set firewall group ipv6-address-group VPN-ADDRESSES-v6 address {item}")
            print(f"echo   - added {item}")



def main():
    print(f"echo Starting IPv6 update script...")

    domains_to_resolve = get_domains_from_file(DOMAINS_FILE)

    current_dns_ips = get_ips_for_domains(domains_to_resolve)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    current_filename = f"vpn-addresses-v6-{timestamp}.txt"
    write_ips_to_file(current_dns_ips, OUTPUT_DIR, current_filename)

    new_master_ips = create_master_list_ips(OUTPUT_DIR, "vpn-addresses-v6")

    new_subnets = get_subnets_for_ips(new_master_ips, IPV6_PREFIX_LENGTH)
    new_ranges = convert_subnets_to_ranges(new_subnets)

    vyos_config_items = get_vyos_config_items()

    generate_vyos_commands_diff(new_ranges, vyos_config_items)

    master_filepath = os.path.join(OUTPUT_DIR, MASTER_LIST_FILENAME)
    write_ips_to_file(new_master_ips, OUTPUT_DIR, MASTER_LIST_FILENAME)

    cleanup_old_files(OUTPUT_DIR, FILE_RETENTION_DAYS, "vpn-addresses-v6")

    print(f"echo ")
    print(f"echo Script execution finished.")

if __name__ == "__main__":
    main()
