import numpy as np
import osmnx as ox
import requests
import pyproj
import subprocess
import os
from scipy.interpolate import splprep, splev
from build123d import Location, Vector, BuildSketch, Polygon, loft
from shapely.geometry import MultiLineString, GeometryCollection
import matplotlib.pyplot as plt
# ==========================================
# STEP 1: PYTHON MATH & CAD LOGIC
# ==========================================


def get_osm_centerline(road_name, town, country):
    """Substep 1.1: Fetches 1D centerline from OpenStreetMap."""
    query = f"{road_name}, {town}, {country}"
    distance = 5000
    G = ox.graph_from_address(query, distance, network_type="drive")
    gdf_edges = ox.graph_to_gdfs(G, nodes=False)

    road_edges = gdf_edges[gdf_edges["name"] == road_name]
    if road_edges.empty:
        raise ValueError(f"Road '{road_name}' not found.")

    line = road_edges.geometry.union_all()
    # Check if it's a collection (which has the .geoms attribute)
    if isinstance(line, (MultiLineString, GeometryCollection)):
        # Now the type checker knows .geoms exists
        line = max(line.geoms, key=lambda a: a.length)

    return np.array(list(line.coords))


def fetch_elevations_and_project(lon_lat_points):
    """Substep 1.2: Fetches Z-heights and projects to standard meters (UTM)."""
    # OpenTopoData API limits large requests, chunking may be required for long roads
    locations = "|".join([f"{lat},{lon}" for lon, lat in lon_lat_points])
    url = f"https://api.opentopodata.org/v1/srtm30m?locations={locations}"

    response = requests.get(url).json()
    z_coords = np.array([res["elevation"] for res in response["results"]])

    # Project to standard meters (Using Zone 33 as default, adjust as needed)
    utm_proj = pyproj.Proj(proj="utm", zone=33, ellps="WGS84")
    x, y = utm_proj(lon_lat_points[:, 0], lon_lat_points[:, 1])

    return np.column_stack((x, y, z_coords))


def plot_centerline_raw(coords, road_name="Road"):
    """
    Plots the raw coordinate array and saves it to a PNG file.
    """
    if coords.size == 0:
        print("Error: Coordinate array is empty.")
        return

    # Extract Longitude (X) and Latitude (Y)
    x = coords[:, 0]
    y = coords[:, 1]

    # Create the figure and axis explicitly
    fig, ax = plt.subplots(figsize=(12, 10))

    # 1. Plot the path
    ax.plot(x, y, color="#1f77b4", linewidth=2, label="Path Sequence")
    ax.scatter(x, y, color="black", s=5, alpha=0.3)

    # 2. Mark Start/End
    ax.scatter(x[0], y[0], color="green", s=100, label="Start", zorder=5)
    ax.scatter(x[-1], y[-1], color="red", s=100, label="End", zorder=5)

    # 3. Label some indices for sequence verification
    step = max(1, len(coords) // 20)
    for i in range(0, len(coords), step):
        ax.annotate(str(i), (x[i], y[i]), fontsize=8, alpha=0.7)

    ax.set_aspect("equal")
    ax.set_title(f"Diagnostic Plot: {road_name}")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()

    # --- THE FIX ---
    filename = "road_diagnostic.png"
    # Use the figure object directly to save
    fig.savefig(filename, dpi=300, bbox_inches="tight")

    print(f"\n✅ Diagnostic plot successfully saved to: {os.path.abspath(filename)}")
    plt.close(fig)  # Clean up memory


def calculate_frenet_frames(points_3d, target_speed_ms=25.0, samples=500):
    """Substep 1.3: Fits 3D spline and calculates dynamic banking frames."""
    tck, _ = splprep([points_3d[:, 0], points_3d[:, 1], points_3d[:, 2]], s=5.0)
    u_fine = np.linspace(0, 1, samples)
    x, y, z = splev(u_fine, tck)

    dx, dy, dz = splev(u_fine, tck, der=1)
    d2x, d2y, d2z = splev(u_fine, tck, der=2)

    frames = []
    g = 9.81
    friction = 0.15

    for i in range(samples):
        T = np.array([dx[i], dy[i], dz[i]])
        T = T / np.linalg.norm(T)

        cross_deriv = np.cross([dx[i], dy[i], dz[i]], [d2x[i], d2y[i], d2z[i]])
        curvature = np.linalg.norm(cross_deriv) / (
            np.linalg.norm([dx[i], dy[i], dz[i]]) ** 3
        )
        radius = 1.0 / (curvature + 1e-6)

        banking_angle_rad = 0.0
        if radius < 2000:
            required_tan_theta = (target_speed_ms**2) / (g * radius) - friction
            required_tan_theta = max(0, min(required_tan_theta, 0.2))
            banking_angle_rad = np.arctan(required_tan_theta)

            if d2x[i] * dy[i] - d2y[i] * dx[i] > 0:
                banking_angle_rad = -banking_angle_rad

        Up = np.array([0, 0, 1])
        Right = np.cross(T, Up)
        Right = Right / np.linalg.norm(Right)
        Track_Up = np.cross(Right, T)

        # Apply banking using Rodrigues' rotation formula
        K, v, theta = T, Track_Up, banking_angle_rad
        Banked_Up = (
            v * np.cos(theta)
            + np.cross(K, v) * np.sin(theta)
            + K * np.dot(K, v) * (1 - np.cos(theta))
        )
        Banked_Right = np.cross(T, Banked_Up)

        origin = (x[i], y[i], z[i])
        frames.append((origin, Banked_Up, Banked_Right))

    return frames


def build_cad_solid(frames, track_width=10.0, track_thickness=2.0):
    """Substep 1.4: Lofts 2D cross-sections into a continuous mathematically smooth solid."""
    cross_sections = []

    for origin, z_dir, x_dir in frames:
        loc = Location(Vector(origin), Vector(x_dir), Vector(z_dir))
        with BuildSketch(loc) as profile:
            hw = track_width / 2.0
            t = track_thickness
            crown = 0.1
            Polygon([(0, 0), (hw, -crown), (hw, -t), (-hw, -t), (-hw, -crown), (0, 0)])
        cross_sections.append(profile.sketch)

    # Output pure CAD logic (B-Rep)
    return loft(cross_sections)


# ==========================================
# STEP 2: STL EXPORT
# ==========================================


def export_solid_to_stl(solid_obj, stl_filename, mesh_tolerance=0.05):
    """Substep 2.1: Discretizes the CAD math into triangles for game engine delivery."""
    # build123d exports exactly to STL, controlling resolution with tolerance
    solid_obj.export_stl(stl_filename, tolerance=mesh_tolerance)
    print(f"Exported intermediary STL mesh to {stl_filename}")


# ==========================================
# STEP 3: BLENDER FBX CONVERSION
# ==========================================


def trigger_blender_conversion(stl_path, fbx_path, blender_executable="blender"):
    """Substep 3.5: Calls headless Blender via Subprocess."""
    script_name = "blender_processor.py"

    if not os.path.exists(script_name):
        raise FileNotFoundError(
            f"Missing {script_name}. Ensure it is in the same directory."
        )

    cmd = [
        blender_executable,
        "--background",
        "--python",
        script_name,
        "--",
        stl_path,
        fbx_path,
    ]

    print("Launching headless Blender process...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Blender Error:")
        print(result.stderr)
    else:
        print(f"Blender conversion successful. Final file: {fbx_path}")


# ==========================================
# PIPELINE EXECUTION
# ==========================================

if __name__ == "__main__":
    # Parameters
    ROAD = "Pikes Peak Highway"
    TOWN = "Cascade"
    COUNTRY = "USA"
    SPEED_MS = 25.0
    TMP_STL = "temp_track.stl"
    FINAL_FBX = "Assetto_Corsa_Track.fbx"

    # Make sure you provide the full path to Blender if it is not in your system PATH.
    # Example: BLENDER_PATH = r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
    BLENDER_PATH = "blender"

    try:
        # Phase 1: CAD Logic
        print("1.1 Fetching centerline...")
        pts_wgs84 = get_osm_centerline(ROAD, TOWN, COUNTRY)
        print(pts_wgs84)
        plot_centerline_raw(pts_wgs84)

        # print(
        #    "1.2 Fetching elevations (Slicing to first 50 points to prevent API rate limits)..."
        # )
        # pts_3d = fetch_elevations_and_project(pts_wgs84[:50])

        # print("1.3 Calculating dynamic banking frames...")
        # frames = calculate_frenet_frames(pts_3d, target_speed_ms=SPEED_MS)

        # print("1.4 Generating mathematically continuous CAD solid...")
        # track_cad = build_cad_solid(frames)

        # Phase 2: Mesh Triangulation
        # print("2.1 Discretizing CAD solid to STL mesh...")
        # export_solid_to_stl(track_cad, TMP_STL, mesh_tolerance=0.05)

        # Phase 3: Blender Conversion
        # print("3.1 Initiating Blender FBX processing...")
        # trigger_blender_conversion(TMP_STL, FINAL_FBX, blender_executable=BLENDER_PATH)

        # print("\nPIPELINE COMPLETE.")

    except Exception as e:
        print(f"Pipeline failed: {e}")
