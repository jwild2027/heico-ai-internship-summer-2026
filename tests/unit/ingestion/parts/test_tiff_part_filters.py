from tiff.part_filters import (
    is_bad_nomenclature,
    is_probable_real_part_number,
    canonicalize_nomenclature_for_comparison,
)


def test_rejects_ata_reference_as_part():
    assert not is_probable_real_part_number("25-21-00-46")
    assert not is_probable_real_part_number("25-IPL")
    assert not is_probable_real_part_number("120TP250008.MCE")


def test_accepts_real_part_families():
    assert is_probable_real_part_number("120-37313-001")
    assert is_probable_real_part_number("AM03078-22")
    assert is_probable_real_part_number("AN960-8L")
    assert is_probable_real_part_number("595-37038")


def test_rejects_bad_nomenclature_noise():
    assert is_bad_nomenclature("T.P")
    assert is_bad_nomenclature("IGURE")
    assert is_bad_nomenclature("SHEET")
    assert is_bad_nomenclature("PER STOCK")
    assert not is_bad_nomenclature("HOLDER, MAGAZINE")


def test_canonicalizes_ocr_tail():
    assert canonicalize_nomenclature_for_comparison("HOLDER, MAGAZINE VS4956") == "HOLDER, MAGAZINE"
