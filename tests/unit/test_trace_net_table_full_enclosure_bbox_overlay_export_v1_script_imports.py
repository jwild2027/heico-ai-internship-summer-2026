def test_script_modules_import():
    import scripts.build.tables.build_trace_net_table_full_enclosure_bbox_overlay_export_v1 as build_script
    import scripts.maintenance.tables.check_trace_net_table_full_enclosure_bbox_overlay_export_v1_quality as check_script

    assert build_script.main
    assert check_script.main
