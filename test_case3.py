#!/usr/bin/env python3
"""Test case 3: Profile-based OD turning"""

import sys
import json
sys.path.insert(0, 'api')

# Pure data loading first
with open('data/input/case3_profile.json') as f:
    data = json.load(f)

print("=" * 60)
print("TEST CASE 3: Profile-based OD Turning")
print("=" * 60)
print()

# Show input data
print("[INPUT]")
print(f"Stock: {data['stock']}")
print(f"Operation: {data['operations'][0]['op']}")
profile = data['operations'][0]['params']['profile']
print(f"Profile points:")
for i, p in enumerate(profile):
    print(f"  [{i}] z={p['z']:5.1f}, d={p['d']:5.1f}  →  z_profile={p['z']:5.1f}, r={p['d']/2:5.1f}")
print()

# Now import CadQuery and modules
try:
    import cadquery as cq
    from api.cad_ops import build_stock, apply_op, _parse_profile_points, _profile_to_world, _lathe_axis_info
    print("[IMPORTS] OK: CadQuery and CAD ops loaded")
    print()
except ImportError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# Build initial stock
print("[STOCK BUILD]")
stock_dict = data['stock']
stock_dict_typed = {
    'type': stock_dict['type'],
    'params': {k: float(v) for k, v in stock_dict['params'].items()}
}

before = build_stock(type('Stock', (), stock_dict_typed))
bb = before.val().BoundingBox()
zmin, zmax, stock_r = _lathe_axis_info(before)

print(f"Stock BBox:")
print(f"  X: [{bb.xmin:.2f}, {bb.xmax:.2f}]")
print(f"  Y: [{bb.ymin:.2f}, {bb.ymax:.2f}]")
print(f"  Z: [{bb.zmin:.2f}, {bb.zmax:.2f}]")
print(f"Lathe axis info: zmin={zmin:.2f}, zmax={zmax:.2f}, radius={stock_r:.2f}")
print()

# Simulate profile analysis
print("[PROFILE ANALYSIS]")
print(f"Profile points (z_profile, r):")
profile_zr = []
for i, p in enumerate(profile):
    z_prof = p['z']
    d = p['d']
    r = d / 2.0
    z_world = zmin + z_prof
    profile_zr.append((z_prof, r))
    print(f"  [{i}] z_prof={z_prof:5.1f} → z_world={z_world:6.2f}, r={r:5.1f}, d={d:5.1f}")

print()
print(f"Profile range in world coords:")
z_worlds = [zmin + z_prof for z_prof, _ in profile_zr]
print(f"  z_world: [{min(z_worlds):.2f}, {max(z_worlds):.2f}]")
print(f"  Stock z_world: [{zmin:.2f}, {zmax:.2f}]")
print(f"  ⚠ Profile ends at z_world={max(z_worlds):.2f}, stock continues to z_world={zmax:.2f}")
print()

print("[ANALYSIS]")
print("When revolving the profile to create a solid:")
print(f"  Profile 2D loop closes at z_world={max(z_worlds):.2f}")
print(f"  revolve(360°) creates a solid that extends from z_world={min(z_worlds):.2f} to {max(z_worlds):.2f}")
print()
print("OD operation: before.intersect(profile_solid)")
print("  → Profile solid has no volume beyond z_world={:.2f}".format(max(z_worlds)))
print("  → Stock beyond that z is NOT in the intersection")
print(f"  → Expected: Only z_world ∈ [{min(z_worlds):.2f}, {max(z_worlds):.2f}] remains")
print()

print("SOLUTION:")
print("  Extend the last profile point to z_world={:.2f}".format(zmax))
print("  Example: add {{ z: {:.1f}, d: {:.1f} }}".format(
    zmax - zmin, profile[-1]['d']
))
print()
print("=" * 60)
