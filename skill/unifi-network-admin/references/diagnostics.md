# Diagnostic workflows

## One client is slow or offline

1. Find the client and record whether it is wired, wireless, or VPN-connected.
2. Identify its reported attachment device when available.
3. Compare the client with another client on the same attachment and network.
4. Check the attachment device state, model, firmware, and returned interface facts.
5. Check the assigned network/VLAN and relevant policy records.
6. Separate a client-only problem from an attachment, VLAN, gateway, DNS, or WAN problem.

Do not diagnose cable quality, RF interference, or DHCP history when the API returned no measurement for it. Give the user a test that would produce that evidence.

## Wi-Fi is slow or unstable

1. Establish the affected site, SSID, clients, time window, and whether wired service is healthy.
2. List Wi-Fi broadcasts, AP devices, and affected connected clients.
3. Get details for the affected clients and APs. Get the latest AP statistics when that capability is available.
4. Use returned radio, channel, width, signal, utilization, retry, or attachment fields when present.
5. Check AP uplink state before blaming RF.
6. Compare affected and unaffected clients by AP, band, and network.
7. Rank RF contention, weak signal, client capability, AP uplink, VLAN/policy, DNS, and WAN only where evidence supports them.

Do not recommend fixed channels, power, widths, or minimum data rates without a local RF measurement and a reason tied to it.

If the complaint includes Internet performance, also run the controlled wired comparison in **Internet or WAN is slow**. Wi-Fi radio data alone does not test the full path.

## Internet or WAN is slow

1. Confirm whether the scope is one client, one network, one site, or every site.
2. Compare wired and wireless paths.
3. Inspect gateway and WAN definitions, device state, and negotiated link facts when returned.
4. Check exposed firewall and DNS policy. Treat traffic-shaping or VPN-policy effects as unavailable unless another returned record provides that evidence.
5. Ask for a controlled wired test when the API cannot measure throughput itself.
6. State whether the evidence points to LAN attachment, gateway processing, DNS, or upstream service.

## VLAN or policy review

1. List networks, VLAN IDs, firewall zones and policies, ACL rules, and DNS policies supported by the site.
2. Trace the intended source, destination, direction, and default behavior.
3. Flag missing data instead of treating an unavailable rule family as empty.
4. Describe effective-access uncertainty when the API returns objects but not evaluation order or references.
5. Keep review and remediation separate; this release cannot apply the proposed fix.
