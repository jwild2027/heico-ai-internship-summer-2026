def test_script_imports():
    import scripts.build_trace_net_figure_item_fast_answer_composer_v1 as build_script
    import scripts.check_trace_net_figure_item_fast_answer_composer_v1_quality as check_script
    assert build_script.main_build
    assert check_script.main_check
