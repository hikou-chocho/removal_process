jimport sys
import struct
import os


def inspect_stl(path):
    with open(path, 'rb') as f:
        header = f.read(80)
        rest = f.read()
    # Heuristic: if header starts with 'solid' and contains ascii 'facet', treat as ASCII
    if header[:5].lower() == b'solid' and b'facet' in rest[:2000].lower():
        # ASCII parse
        coords = []
        with open(path, 'r', errors='ignore') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 4 and parts[0].lower() == 'vertex':
                    try:
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        coords.append((x, y, z))
                    except Exception:
                        pass
    else:
        # binary STL
        coords = []
        if len(rest) < 4:
            print('No triangles')
            return
        num_tris = struct.unpack('<I', rest[:4])[0]
        offs = 4
        for i in range(num_tris):
            if offs + 50 > len(rest):
                break
            # each triangle: normal(3f), v1(3f), v2(3f), v3(3f), attr(2)
            data = rest[offs:offs+50]
            vals = struct.unpack('<12fH', data)
            # vertices at positions 3..11
            v1 = (vals[3], vals[4], vals[5])
            v2 = (vals[6], vals[7], vals[8])
            v3 = (vals[9], vals[10], vals[11])
            coords.extend([v1, v2, v3])
            offs += 50

    if not coords:
        print('No vertices found in', path)
        return
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    cx = sum(xs)/len(xs)
    cy = sum(ys)/len(ys)
    cz = sum(zs)/len(zs)
    print('FILE:', path)
    print('  COUNT vertices:', len(coords))
    print(f'  X: {xmin:.6f} .. {xmax:.6f}  Y: {ymin:.6f} .. {ymax:.6f}  Z: {zmin:.6f} .. {zmax:.6f}')
    print(f'  CENTROID: ({cx:.6f}, {cy:.6f}, {cz:.6f})')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: inspect_stl.py file1.stl [file2.stl ...]')
        sys.exit(1)
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print('Not found:', p)
            continue
        inspect_stl(p)
