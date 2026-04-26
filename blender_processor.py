import bpy
import sys


def clean_scene():
    """Substep 3.1: Clears default Blender objects."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_and_setup_mesh(input_stl):
    """Substep 3.2: Imports STL and renames for Assetto Corsa physics."""
    bpy.ops.import_mesh.stl(filepath=input_stl)

    # Grab the imported object
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj

    # Assetto Corsa naming convention for drivable asphalt
    obj.name = "1ROAD_asphalt"
    return obj


def apply_uv_mapping(obj):
    """Substep 3.3: Applies procedural UV mapping for textures."""
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    # Smart UV project works well for basic track texturing
    bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")


def export_to_fbx(output_fbx):
    """Substep 3.4: Exports the scene to FBX with Game Engine axes."""
    bpy.ops.export_scene.fbx(
        filepath=output_fbx,
        use_selection=True,
        axis_forward="-Z",
        axis_up="Y",
        apply_scale_options="FBX_SCALE_ALL",
    )


if __name__ == "__main__":
    # Extract arguments passed after "--"
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
        input_path = argv[0]
        output_path = argv[1]

        clean_scene()
        track_obj = import_and_setup_mesh(input_path)
        apply_uv_mapping(track_obj)
        export_to_fbx(output_path)

        print(f"SUCCESS: Blender exported {output_path}")
