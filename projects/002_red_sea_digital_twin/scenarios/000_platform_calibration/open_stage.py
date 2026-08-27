"""Open the calibration stage and bind its overview camera at Kit startup."""

import argparse

import carb
import omni.client
import omni.kit.async_engine
import omni.usd


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Absolute path to the USD stage")
    parser.add_argument("--camera", help="Camera prim to bind after opening")
    return parser.parse_args()


async def open_stage(path, camera_path):
    result, _ = await omni.client.stat_async(path)
    if result != omni.client.Result.OK:
        carb.log_error(f"AUV stage does not exist: {path}")
        return

    success, error = await omni.usd.get_context().open_stage_async(path)
    if not success:
        carb.log_error(f"AUV stage failed to open: {path}: {error}")
        return

    carb.log_info(f"AUV stage opened: {path}")

    if camera_path:
        from omni.kit.viewport.utility import get_active_viewport

        viewport = get_active_viewport()
        if viewport is None:
            carb.log_warn("AUV stage opened, but no active viewport accepted the camera")
        else:
            viewport.camera_path = camera_path
            carb.log_info(f"AUV overview camera bound: {camera_path}")


options = parse_args()
omni.kit.async_engine.run_coroutine(open_stage(options.path, options.camera))
