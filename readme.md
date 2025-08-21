This script takes a list of domains, finds every IP range associated with them, and adds them to VyOS firewall groups. The intended use case is VPN split tunnelling; I wrote this when the new ~~surveillance~~ ~~I mean censorship~~ I mean "protecting children" law came into effect in the UK and I wanted to pass all social media traffic from my home network through ProtonVPN.

A lot of VPN apps have split tunnelling built in, but if your network setup is more complicated than most - say, like me, you run your own DNS server and use Tailscale to connect your mobile devices to self-hosted services - then a router-level approach like this may be best.

You'll need to download the .py and .script files and place them in /config/scripts. Then create a text file at /config/scripts/vpn_domains.txt with a list of domains - one per line - you want the script to track. Finally, create a task scheduler job in your VyOS config to run the .script file regularly; I'd recommend once a week or so, as ASN allocations don't change very often.

Note that this script does not actually apply any routing policies, it just creates the groups. You'll need to do the routing and set up the VPN connection separately.
