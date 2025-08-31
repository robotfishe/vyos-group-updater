This set of scripts takes a list of domains, finds IP ranges associated with them, and adds them to VyOS firewall groups. The intended use case is VPN split tunnelling; I wrote this when the new ~~surveillance~~ ~~I mean censorship~~ I mean "protecting children" law came into effect in the UK and I wanted to pass all social media traffic from my home network through ProtonVPN.

A lot of VPN apps have split tunnelling built in, but if your network setup is more complicated than most - say, like me, you run your own DNS server and use Tailscale to connect your mobile devices to self-hosted services - then a router-level approach like this may be best.

There are two approaches used here. One uses ASNs (Autonomous System Numbers) to pull IP ranges for very large entities (e.g., Facebook). Those ranges are public record and don't change very often.

The other uses DNS results gathered over time to make an educated guess at IP ranges representing smaller sites. This less precise approach is necessary because these sites may be using third-party content delivery networks. For example, if you search for the ASN associated with signal.org, you actually get Cloudflare's ASN, which covers thousands of other sites.

You'll need to download the .py and .script files and place them in /config/scripts.

Then create two text file at /config/scripts/vpn_domains_asn.txt and /config/scripts/vpn_domains_dns.txt. These each contain a list of domains - one per line - you want the script to track. Check manually before you add anything to the ASN list; there are very few websites that actually have their own ASNs.

Finally, create a task scheduler job in your VyOS config to run each .script file regularly. I'd recommend running the ASN script once a week and the DNS script every 15 minutes.

Note that this script does not actually apply any routing policies, it just creates the groups. You'll need to do the routing and set up the VPN connection separately.
