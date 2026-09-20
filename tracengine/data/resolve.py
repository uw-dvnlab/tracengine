"""
TRACE Channel Resolution

Unified resolution logic for annotators and compute modules.
Resolves ChannelSpec declarations to actual Channel references.
"""

from tracengine.data.descriptors import (
    RunData,
    Channel,
    ChannelSpec,
    RunConfig,
    EventSpec,
    Event,
)


def resolve_channel(
    run: RunData,
    spec: ChannelSpec,
    config: RunConfig | None = None,
    instance_name: str | None = None,
) -> Channel:
    """
    Resolve a ChannelSpec to a specific Channel.

    Resolution order:
    1. Exact match from config binding (if config and instance_name provided)
    2. Derived version (suffix matching: _bf*, _sg, _d*, etc.)
    3. Raise KeyError if not found

    Args:
        run: The RunData containing signals
        spec: The ChannelSpec to resolve
        config: Optional RunConfig with pre-set bindings
        instance_name: Instance name to look up bindings for

    Returns:
        Channel reference

    Raises:
        KeyError: If no matching channel found
    """
    # Check config binding first (nested by instance name)
    if config and instance_name and instance_name in config.channel_bindings:
        instance_bindings = config.channel_bindings[instance_name]
        if spec.semantic_role in instance_bindings:
            channel_id = instance_bindings[spec.semantic_role]
            print(channel_id)
            if ":" in channel_id:
                group, name = channel_id.split(":", 1)
                if group in run.signals and name in run.signals[group].data.columns:
                    channels = run.signals[group].list_channels()
                    print(channels)
                    # If allow_derived, prefer derived versions
                    # TODO: Re-enable with separate allow_filtered/allow_derivative flags
                    # See TODO.md for details
                    if spec.allow_derived:
                        derived_match = (
                            None  # Disabled: users must specify exact channel
                        )
                        if derived_match:
                            print(f"Using derived channel for {name}: {derived_match}")
                            return Channel.from_parts(group, derived_match)
                        else:
                            print(f"No derived channel found for {name}")
                    return Channel.from_parts(group, name)

    raise KeyError(
        f"No channel found for spec: semantic_role='{spec.semantic_role}' "
        f"(instance='{instance_name}')"
    )


def _find_derived_channel(channels: list[str], base_name: str) -> str | None:
    """
    Find the most derived version of a channel.

    Preference order (highest to lowest):
    1. Filtered + derivative: base_bf*_d*
    2. Derivative: base_d*
    3. Filtered: base_bf*, base_sg, etc.
    4. Base channel

    Returns the channel name or None if no match.
    """
    # Build list of candidates that start with base_name
    candidates = [ch for ch in channels if ch.startswith(base_name)]

    if not candidates:
        return None

    # Score each candidate (higher = more derived)
    def score(ch: str) -> int:
        s = 0
        suffix = ch[len(base_name) :]
        if "_bf" in suffix or "_sg" in suffix or "_rm" in suffix:
            s += 10  # Filtered
        if "_d" in suffix:
            s += 5  # Derivative
        if "_dt" in suffix:
            s += 3  # Detrend
        if "_rs" in suffix:
            s += 2  # Resample
        return s

    # Sort by score descending, prefer most derived
    candidates.sort(key=score, reverse=True)

    # Return most derived, or base if no processing
    return candidates[0] if candidates else None


def resolve_all(
    run: RunData,
    specs: dict[str, ChannelSpec],
    config: RunConfig | None = None,
    instance_name: str | None = None,
) -> dict[str, Channel]:
    """
    Resolve all ChannelSpecs for a plugin.

    Args:
        run: The RunData containing signals
        specs: Dict of role_name -> ChannelSpec
        config: Optional RunConfig with pre-set bindings
        instance_name: Instance name to look up bindings for

    Returns:
        Dict of role_name -> resolved Channel

    Raises:
        KeyError: If any required spec cannot be resolved
    """
    use_config = config or run.run_config

    resolved = {}
    for role, spec in specs.items():
        resolved[role] = resolve_channel(run, spec, use_config, instance_name)

    return resolved


def resolve_events(
    run: RunData,
    event_specs: dict[str, "EventSpec"],
    config: RunConfig | None = None,
    instance_name: str | None = None,
) -> dict[str, list["Event"]]:
    """
    Resolve EventSpecs to actual event lists.

    Args:
        run: The RunData containing annotations
        event_specs: Dict of role_name -> EventSpec
        config: Optional RunConfig with pre-set bindings
        instance_name: Instance name to look up bindings for

    Returns:
        Dict of role_name -> list of Event objects
    """
    resolved = {}
    print(event_specs)
    for role, spec in event_specs.items():
        # 1. Check config binding first
        binding_found = False
        if config and instance_name and instance_name in config.event_bindings:
            instance_bindings = config.event_bindings[instance_name]
            if role in instance_bindings:
                group_name = instance_bindings[role]
                if spec.optional and group_name == "":
                    resolved[role] = None
                    continue
                if spec.optional and group_name not in run.annotations:
                    raise KeyError(f"Bound event group '{group_name}' is missing for '{role}'; rebind or select None")
                if group_name in run.annotations:
                    resolved[role] = run.annotations[group_name]
                    binding_found = True
                    print(f"Using bound event group '{group_name}' for role '{role}'")
                else:
                    print(
                        f"Warning: Bound event group '{group_name}' not found for role '{role}'"
                    )

        if binding_found:
            continue

        if spec.optional:
            resolved[role] = None
            continue

        # 2. Fallback: Search annotations for matching event_type (first match)
        for group_name, events in run.annotations.items():
            if events and events[0].event_type == spec.event_type:
                resolved[role] = events
                print(
                    f"Auto-resolved event group '{group_name}' for role '{role}' (type match)"
                )
                break
        else:
            raise KeyError(
                f"No events found matching EventSpec: {spec} (role='{role}', instance='{instance_name}')"
            )

    return resolved
