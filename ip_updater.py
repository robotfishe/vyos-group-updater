import subprocess
import re
import ipaddress
import sys
import time

# --- config ---
domains_file = "/config/scripts/vpn_domains.txt"
ipv4_group_name = "VPN-NETWORKS"
ipv6_group_name = "VPN-NETWORKS-v6"
config_path = "/config/config.boot"

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
        print(f"echo Please create a file named {filepath} with one domain per line.")
    except IOError as e:
        print(f"echo Error reading file {filepath}: {e}")

    return domains

def get_ip_from_domain(domain):
    try:
        command = ["dig", "+short", domain]
        result = subprocess.run(command, capture_output=True, text=True, check=True)

        ips = result.stdout.strip().split('\n')

        if ips[0]:
            try:
                ipaddress.ip_address(ips[0])
                print(f"echo Found IP for {domain}: {ips[0]}")
                return ips[0]
            except ValueError:
                print(f"echo Skipping non-IP address for {domain}: {ips[0]}")
                return None

    except subprocess.CalledProcessError as e:
        print(f"echo Error during dig lookup for {domain}: {e.stderr}")
    except Exception as e:
        print(f"echo An unexpected error occurred: {e}")

    return None

def get_asn_from_ip(ip_address):
    try:
        command = f'echo " -v {ip_address}" | nc whois.cymru.com 43'

        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True)

        lines = result.stdout.strip().split('\n')

        if len(lines) > 1:
            data_line = lines[1]
            parts = data_line.split('|')
            if len(parts) >= 1:
                print(f"echo Found ASN for {ip_address}: {parts[0].strip()}")
                return parts[0].strip()

    except subprocess.CalledProcessError as e:
        print(f"echo Error during whois lookup: {e.stderr}")
    except Exception as e:
        print(f"echo An unexpected error occurred: {e}")

    return None

def get_networks_from_asn(asn):
    max_retries = 2
    print(f"echo Getting networks for ASN {asn}")

    for attempt in range(max_retries + 1):
        try:
            command = ["whois", "-h", "whois.radb.net", "-i", "origin", f"AS{asn}"]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)

            details = {
                "ipv4_networks": set(),
                "ipv6_networks": set()
            }

            for line in result.stdout.splitlines():
                route_match = re.search(r"route:\s*(.*)", line)
                if route_match:
                    details["ipv4_networks"].add(route_match.group(1).strip())
                    print(f"echo Found ipv4 network: {route_match.group(1).strip()}")

                route6_match = re.search(r"route6:\s*(.*)", line)
                if route6_match:
                    details["ipv6_networks"].add(route6_match.group(1).strip())
                    print(f"echo Found ipv6 network: {route6_match.group(1).strip()}")

            return details

        except subprocess.CalledProcessError as e:
            print(f"echo Error during RADB lookup: {e.stderr.strip()}")
            if attempt < max_retries:
                print(f"echo Retrying in 10 seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(20)
            else:
                print("echo Max retries exceeded. Exiting.")

        except subprocess.TimeoutExpired as e:
            print(f"echo Command timed out after {e.timeout} seconds.")
            if attempt < max_retries:
                print(f"echo Retrying in 10 seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(20)
            else:
                print("echo Max retries exceeded. Exiting.")

        except Exception as e:
            print(f"echo An unexpected error occurred: {e}")
            if attempt < max_retries:
                print(f"echo Retrying in 10 seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(10)
            else:
                print("echo Max retries exceeded. Exiting.")

    return None

def get_current_group_networks(group_name, is_ipv6=False):
    current_items = set()
    group_type = "ipv6-network-group" if is_ipv6 else "network-group"
    group_name = ipv6_group_name if is_ipv6 else ipv4_group_name

    print(f"echo Looking for existing entries in {group_type} {group_name}")

    in_address_group = False

    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if f'{group_type} {group_name} {{' in line:
                    in_address_group = True
                elif in_address_group and line == '}':
                    in_address_group = False
                elif in_address_group and line.startswith('network '):
                    ip_item = line.split(' ')[1].strip('\'" ')
                    current_items.add(ip_item)
                    print(f"echo Found existing IPv6 address/prefix {ip_item}")
    except IOError as e:
        print(f"echo Error reading VyOS config file {config_path}: {e}")
        print(f"echo Assuming no IPv6 IPs are currently configured.")

    return current_items

def main():
    domains = get_domains_from_file(domains_file)

    if not domains:
        print(f"echo No domains found in {domains_file}. Exiting.")
        sys.exit(1)

    # Get IPs from domains in text file
    all_ips = set()
    print("echo Performing DNS lookups for all domains...")
    for domain in domains:
        ip_address = get_ip_from_domain(domain)
        if ip_address:
            all_ips.add(ip_address)

    # Get ASNs from IPs
    all_asns = set()
    print("echo Finding unique ASNs for all IPs...")
    for ip_address in all_ips:
        asn = get_asn_from_ip(ip_address)
        if asn:
            all_asns.add(asn)

    # Get all networks from ASNs
    all_ipv4_networks = set()
    all_ipv6_networks = set()
    print("echo Retrieving all networks for the identified ASNs...")
    for i, asn in enumerate(all_asns):
        asn_networks = get_networks_from_asn(asn)
        if asn_networks:
            all_ipv4_networks.update(asn_networks["ipv4_networks"])
            all_ipv6_networks.update(asn_networks["ipv6_networks"])
        if i < len(all_asns) - 1:
            print(f"echo Waiting 20 seconds before retrieving next network set")
            time.sleep(20)

    # Aggregate
    print("echo Aggregating IP ranges for a more efficient configuration...")
    ipv4_networks = [ipaddress.ip_network(p, strict=False) for p in all_ipv4_networks]
    ipv6_networks = [ipaddress.ip_network(p, strict=False) for p in all_ipv6_networks]
    collapsed_ipv4 = set(str(net) for net in ipaddress.collapse_addresses(ipv4_networks))
    collapsed_ipv6 = set(str(net) for net in ipaddress.collapse_addresses(ipv6_networks))

    # Get current networks from router config
    current_ipv4 = get_current_group_networks(ipv4_group_name, is_ipv6=False)
    current_ipv6 = get_current_group_networks(ipv6_group_name, is_ipv6=True)

    # Determine networks to add and remove
    ipv4_to_add = collapsed_ipv4 - current_ipv4
    ipv4_to_remove = current_ipv4 - collapsed_ipv4
    ipv6_to_add = collapsed_ipv6 - current_ipv6
    ipv6_to_remove = current_ipv6 - collapsed_ipv6

    # Generate VyOS commands
    if ipv4_to_remove:
        print("echo Deleting obsolete IPv4 network ranges...")
        for network in sorted(list(ipv4_to_remove)):
            print(f"delete firewall group network-group {ipv4_group_name} network {network}")
    if ipv6_to_remove:
        print("echo Deleting obsolete IPv6 network ranges...")
        for network in sorted(list(ipv6_to_remove)):
            print(f"delete firewall group ipv6-network-group {ipv6_group_name} network {network}")
    if ipv4_to_add:
        print("echo Adding new IPv4 network ranges...")
        for network in sorted(list(ipv4_to_add)):
            print(f"echo Adding {network}")
            print(f"set firewall group network-group {ipv4_group_name} network {network}")
    if ipv6_to_add:
        print("echo Adding new IPv6 network ranges...")
        for network in sorted(list(ipv6_to_add)):
            print(f"set firewall group ipv6-network-group {ipv6_group_name} network {network}")

if __name__ == "__main__":
    main()
