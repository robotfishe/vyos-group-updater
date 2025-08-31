This set of scripts takes a list of domains, finds IP ranges associated with them, and adds them to VyOS firewall groups. The intended use case is VPN split tunnelling; I wrote this when the new ~~surveillance~~ ~~I mean censorship~~ I mean "protecting children" law came into effect in the UK and I wanted to pass all social media traffic from my home network through ProtonVPN.

A lot of VPN apps have split tunnelling built in, but there are two major issues with that:
1. Generally, VPN app split tunnelling divides traffic based on a variable at your end of the connection, not based on the destination. So you can do "Firefox uses a VPN but Chrome doesn't", but you can't do "YouTube uses a VPN but The Weather Network doesn't". That's what this setup accomplishes.
2. If your network setup is more complicated than most - say, like me, you run your own DNS server and use Tailscale to connect your mobile devices to self-hosted services - you may want all your traffic to reach your router unimpeded and only be divided into VPN and non-VPN when it leaves your network.

So, while a setup like this isn't for everyone, it does have its advantages.

There are two approaches used here. One uses ASNs (Autonomous System Numbers) to pull IP ranges for very large entities (e.g., Facebook). Those ranges are public record and don't change very often.

The other uses DNS results gathered over time to make an educated guess at IP ranges representing smaller sites. This less precise approach is necessary because these sites may be using third-party content delivery networks. For example, if you search for the ASN associated with signal.org, you actually get Cloudflare's ASN, which covers thousands of other sites.

You'll need to download the .py and .script files and place them in /config/scripts.

Then create two text files at /config/scripts/vpn_domains_asn.txt and /config/scripts/vpn_domains_dns.txt. These should each contain a list of domains - one per line - you want the script to track. Check manually before you add anything to the ASN list; there are very few websites that actually have their own ASNs.

Finally, create a task scheduler job in your VyOS config to run each .script file regularly. I'd recommend running the ASN script once a week and the DNS script every 15 minutes.

Note that these scripts do not actually apply any routing policies, they just create the groups. You'll need to do the routing and set up the VPN connection separately.

Also, BIG IMPORTANT NOTICE that this setup is NOT designed for maximum security, it is designed for maximum ease of use. It does not prevent your DNS searches from leaking to your ISP. It does not prevent your identity from being tracked across sites through browser fingerprinting etc. You will probably get the occasional failure where the script hasn't caught every IP address for a service and you accidentally connect without going through the VPN. 
