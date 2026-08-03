from __future__ import annotations


def test_script_imports() -> None:
    import scripts.build.visual.build_trace_net_e2e_image_visual_observer_route_v34_3  # noqa: F401
    import scripts.maintenance.visual.check_trace_net_e2e_image_visual_observer_route_v34_3_quality  # noqa: F401
    import scripts.operations.visual.serve_trace_net_e2e_image_visual_observer_route_v34_3  # noqa: F401
