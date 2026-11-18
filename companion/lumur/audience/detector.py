"""Derive presence / zone / gathering events from tracked people.

Uses ankle→floor projection (same as footsteps) so zone coordinates share the
floor u/v frame with ``position_floor``. Gathering fires when N people share a
zone (or proximity cluster) for a dwell time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


from lumur.audience.events import AudienceEvent
from lumur.audience.zones import FloorZone, point_in_zone
from lumur.track.footsteps import FootstepDetector, FootstepEvent
from lumur.track.tracker import PersonTrack


FloorLocator = Callable[[PersonTrack], tuple[float, float] | None]


@dataclass
class AudienceState:
    """Snapshot of who is where — available to metaprompts / ambience."""

    timestamp: float = 0.0
    person_ids: tuple[int, ...] = ()
    count: int = 0
    # person_id → floor (u, v)
    positions: dict[int, tuple[float, float]] = field(default_factory=dict)
    # zone_id → person_ids currently inside
    occupants: dict[str, tuple[int, ...]] = field(default_factory=dict)
    # Active gatherings: cluster/zone id → person_ids
    gatherings: dict[str, tuple[int, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": float(self.timestamp),
            "person_ids": list(self.person_ids),
            "count": int(self.count),
            "positions": {
                str(k): [float(v[0]), float(v[1])] for k, v in self.positions.items()
            },
            "occupants": {k: list(v) for k, v in self.occupants.items()},
            "gatherings": {k: list(v) for k, v in self.gatherings.items()},
        }

    def summary_text(self) -> str:
        """Short structured prose for scenario metaprompt injection."""
        if self.count == 0:
            return "Audience: empty room."
        parts = [f"Audience: {self.count} present (ids {list(self.person_ids)})."]
        for zid, pids in sorted(self.occupants.items()):
            if pids:
                parts.append(f"Zone {zid}: {list(pids)}.")
        for gid, pids in sorted(self.gatherings.items()):
            if pids:
                parts.append(f"Gathering {gid}: {list(pids)}.")
        return " ".join(parts)


@dataclass
class _PersonZoneState:
    zones: set[str] = field(default_factory=set)
    # zone_id → first continuous enter time
    enter_t: dict[str, float] = field(default_factory=dict)


@dataclass
class AudienceDetector:
    """Track occupancy of floor zones and emit audience events.

    Parameters
    ----------
    zones:
        Named interaction zones in floor u/v.
    gathering_min_count:
        Minimum concurrent occupants to fire ``gathering``.
    gathering_dwell_s:
        Seconds the count must hold before emitting ``gathering``.
    proximity_radius_m:
        Optional cluster radius when no zone hosts the gathering.
    presence_hysteresis:
        Emit ``presence`` only when the person-id set changes.
    """

    zones: list[FloorZone] = field(default_factory=list)
    gathering_min_count: int = 2
    gathering_dwell_s: float = 1.0
    proximity_radius_m: float = 0.85
    presence_hysteresis: bool = True
    _person_state: dict[int, _PersonZoneState] = field(default_factory=dict)
    _last_presence_ids: tuple[int, ...] = ()
    _gathering_since: dict[str, float] = field(default_factory=dict)
    _active_gatherings: set[str] = field(default_factory=set)
    _last_state: AudienceState = field(default_factory=AudienceState)

    def set_zones(self, zones: list[FloorZone]) -> None:
        self.zones = list(zones)

    @property
    def state(self) -> AudienceState:
        return self._last_state

    def locate_track(
        self,
        track: PersonTrack,
        footstep_detector: FootstepDetector | None,
    ) -> tuple[float, float] | None:
        """Project a track onto the floor via ankles (prefer average of both)."""
        if footstep_detector is None:
            return None
        pts: list[tuple[float, float]] = []
        for foot in ("left", "right"):
            kp = track.ankle(foot)
            if kp is None or not kp.visible:
                continue
            hit = footstep_detector.ankle_to_floor(kp.u, kp.v)
            if hit is None:
                continue
            pos, _ = hit
            pts.append(footstep_detector.floor_uv(pos))
        if not pts:
            # Fall back to hip midpoint if available.
            for name in ("left_hip", "right_hip"):
                kp = track.keypoints.get(name)
                if kp is None or not kp.visible:
                    continue
                hit = footstep_detector.ankle_to_floor(kp.u, kp.v)
                if hit is None:
                    continue
                pos, _ = hit
                pts.append(footstep_detector.floor_uv(pos))
        if not pts:
            return None
        u = float(sum(p[0] for p in pts) / len(pts))
        v = float(sum(p[1] for p in pts) / len(pts))
        return u, v

    def update(
        self,
        tracks: list[PersonTrack],
        timestamp: float,
        *,
        footstep_detector: FootstepDetector | None = None,
        footsteps: list[FootstepEvent] | None = None,
        locator: FloorLocator | None = None,
    ) -> list[AudienceEvent]:
        """Advance occupancy and return newly emitted audience events.

        ``footsteps`` are accepted for API symmetry / recording; this detector
        does not re-emit them (callers forward footstep events separately).
        """
        del footsteps  # recorded by callers; not transformed here
        events: list[AudienceEvent] = []
        positions: dict[int, tuple[float, float]] = {}
        active_ids: list[int] = []

        for track in tracks:
            loc = None
            if locator is not None:
                loc = locator(track)
            else:
                loc = self.locate_track(track, footstep_detector)
            if loc is None:
                continue
            pid = int(track.track_id)
            active_ids.append(pid)
            positions[pid] = loc

        active_ids_t = tuple(sorted(active_ids))

        # Presence when the set of people changes (or first non-empty).
        if (not self.presence_hysteresis) or (active_ids_t != self._last_presence_ids):
            events.append(
                AudienceEvent(
                    type="presence",
                    timestamp=float(timestamp),
                    person_ids=active_ids_t,
                    count=len(active_ids_t),
                )
            )
            self._last_presence_ids = active_ids_t

        # Zone enter / leave.
        occupants: dict[str, list[int]] = {z.zone_id: [] for z in self.zones}
        seen_pids = set(active_ids)

        for pid, (u, v) in positions.items():
            st = self._person_state.setdefault(pid, _PersonZoneState())
            inside_now: set[str] = set()
            for zone in self.zones:
                if point_in_zone(u, v, zone):
                    inside_now.add(zone.zone_id)
                    occupants[zone.zone_id].append(pid)
            entered = inside_now - st.zones
            left = st.zones - inside_now
            for zid in sorted(entered):
                st.enter_t[zid] = float(timestamp)
                events.append(
                    AudienceEvent(
                        type="zone_enter",
                        timestamp=float(timestamp),
                        person_id=pid,
                        person_ids=(pid,),
                        zone_id=zid,
                        count=1,
                        position_floor=(u, v),
                    )
                )
            for zid in sorted(left):
                st.enter_t.pop(zid, None)
                events.append(
                    AudienceEvent(
                        type="zone_leave",
                        timestamp=float(timestamp),
                        person_id=pid,
                        person_ids=(pid,),
                        zone_id=zid,
                        count=1,
                        position_floor=(u, v),
                    )
                )
            st.zones = inside_now

        # Drop state for people who disappeared.
        for pid in list(self._person_state.keys()):
            if pid not in seen_pids:
                st = self._person_state.pop(pid)
                for zid in sorted(st.zones):
                    events.append(
                        AudienceEvent(
                            type="zone_leave",
                            timestamp=float(timestamp),
                            person_id=pid,
                            person_ids=(pid,),
                            zone_id=zid,
                            count=1,
                        )
                    )

        # Gathering: per-zone concurrent occupants with dwell.
        gatherings: dict[str, tuple[int, ...]] = {}
        for zid, pids in occupants.items():
            key = f"zone:{zid}"
            if len(pids) >= self.gathering_min_count:
                if key not in self._gathering_since:
                    self._gathering_since[key] = float(timestamp)
                held = float(timestamp) - self._gathering_since[key]
                if held >= self.gathering_dwell_s:
                    gatherings[key] = tuple(sorted(pids))
                    if key not in self._active_gatherings:
                        self._active_gatherings.add(key)
                        events.append(
                            AudienceEvent(
                                type="gathering",
                                timestamp=float(timestamp),
                                zone_id=zid,
                                cluster_id=key,
                                person_ids=tuple(sorted(pids)),
                                count=len(pids),
                            )
                        )
            else:
                self._gathering_since.pop(key, None)
                self._active_gatherings.discard(key)

        # Proximity clusters when enough people are close (no zone required).
        cluster_gatherings = self._proximity_gatherings(positions, timestamp)
        for cid, pids in cluster_gatherings.items():
            gatherings[cid] = pids
            if cid not in self._active_gatherings:
                self._active_gatherings.add(cid)
                events.append(
                    AudienceEvent(
                        type="gathering",
                        timestamp=float(timestamp),
                        cluster_id=cid,
                        person_ids=pids,
                        count=len(pids),
                    )
                )
        # Clear proximity gatherings that dissolved.
        for cid in list(self._active_gatherings):
            if cid.startswith("prox:") and cid not in cluster_gatherings:
                self._active_gatherings.discard(cid)
                self._gathering_since.pop(cid, None)

        self._last_state = AudienceState(
            timestamp=float(timestamp),
            person_ids=active_ids_t,
            count=len(active_ids_t),
            positions=dict(positions),
            occupants={k: tuple(sorted(v)) for k, v in occupants.items()},
            gatherings=dict(gatherings),
        )
        return events

    def _proximity_gatherings(
        self,
        positions: dict[int, tuple[float, float]],
        timestamp: float,
    ) -> dict[str, tuple[int, ...]]:
        ids = sorted(positions.keys())
        if len(ids) < self.gathering_min_count:
            return {}
        # Union-find by proximity radius.
        parent = {i: i for i in ids}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        r2 = self.proximity_radius_m ** 2
        for i in range(len(ids)):
            ui, vi = positions[ids[i]]
            for j in range(i + 1, len(ids)):
                uj, vj = positions[ids[j]]
                if (ui - uj) ** 2 + (vi - vj) ** 2 <= r2:
                    union(ids[i], ids[j])

        clusters: dict[int, list[int]] = {}
        for pid in ids:
            clusters.setdefault(find(pid), []).append(pid)

        out: dict[str, tuple[int, ...]] = {}
        for root, members in clusters.items():
            if len(members) < self.gathering_min_count:
                continue
            # Stable id from sorted member list.
            cid = "prox:" + "-".join(str(m) for m in sorted(members))
            if cid not in self._gathering_since:
                self._gathering_since[cid] = float(timestamp)
            held = float(timestamp) - self._gathering_since[cid]
            if held >= self.gathering_dwell_s:
                out[cid] = tuple(sorted(members))
            # Keep dwell clock even while below emit threshold.
        # Reset clocks for dissolved prox keys.
        for key in list(self._gathering_since.keys()):
            if key.startswith("prox:") and key not in out:
                # Only clear if cluster membership changed (key encodes members).
                still_building = False
                for root, members in clusters.items():
                    cand = "prox:" + "-".join(str(m) for m in sorted(members))
                    if cand == key:
                        still_building = True
                        break
                if not still_building:
                    self._gathering_since.pop(key, None)
        return out
