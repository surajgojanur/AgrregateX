"""Pure validation for partition target and preserved Docker network attachment data."""
def validate_isolated_target(network, api_networks, shard_networks, shard_b_networks):
    if network not in api_networks or network not in shard_networks:
        raise ValueError("API and target shard must both be attached to dedicated target network")
    if network in shard_b_networks:
        raise ValueError("target network also carries shard B; refusing broad partition")
    if not (set(api_networks) - {network}) & set(shard_b_networks):
        raise ValueError("API has no independent network path to shard B")

def attachment_restore_options(attachment):
    """Return aliases and static addresses needed to reconnect a detached container."""
    opts=[]
    for alias in attachment.get("Aliases", []):
        if alias:
            opts.extend(["--alias", alias])
    ipv4=attachment.get("IPv4Address", "").split("/")[0]
    ipv6=attachment.get("IPv6Address", "").split("/")[0]
    if ipv4: opts.extend(["--ip", ipv4])
    if ipv6: opts.extend(["--ip6", ipv6])
    return opts
