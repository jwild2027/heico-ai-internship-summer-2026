from tiff.part_filters import (
    canonicalize_nomenclature_for_comparison,
    is_bad_nomenclature,
    is_probable_real_part_number,
)


def test_ata_and_manual_references_are_not_part_numbers():
    for value in ["25-21-00-46", "25-21-00-105", "25210046", "25-IPL", "25-CONTENTS", "120-25-0224", "120TP250008.MCE"]:
        assert not is_probable_real_part_number(value)


def test_known_part_number_families_still_pass():
    for value in ["120-37313-001", "120-29068-013/051", "AM03078-22", "AN960-8L", "NAS4704-5", "595-37038", "PE21052-2"]:
        assert is_probable_real_part_number(value)


def test_bad_nomenclature_and_ocr_tails_are_cleaned():
    for value in ["T.P", "IGURE", "SHEET", "25-IPL", "PER STOCK"]:
        assert is_bad_nomenclature(value)
    assert canonicalize_nomenclature_for_comparison("HOLDER, MAGAZINE . 0CCEEE") == "HOLDER, MAGAZINE"
    assert canonicalize_nomenclature_for_comparison("HOLDER, MAGAZINE . EE. »=VS4956") == "HOLDER, MAGAZINE"
