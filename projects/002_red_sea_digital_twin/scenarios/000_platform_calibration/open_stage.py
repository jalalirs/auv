"""Open the calibration stage and bind its overview camera at Kit startup."""

import os

import carb
import omni.client
import omni.kit.async_engine
import omni.usd
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


stage_path = os.environ.get("AUV_STAGE_PATH")
camera_path = os.environ.get("AUV_CAMERA_PATH")
if not stage_path:
    carb.log_error("AUV_STAGE_PATH is required")
else:
    omni.kit.async_engine.run_coroutine(open_stage(stage_path, camera_path))
