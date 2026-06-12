from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from tiff.trace_net_dublin_core_source_package_extension_v1 import (
    build_dublin_core_source_package_extension,
    page_number_from_entry_name,
    page_number_from_page_id,
    parse_source_package,
)


def _metadata_xml(files: list[tuple[str, bytes]]) -> str:
    file_nodes = []
    for idx, (name, data) in enumerate(files, start=1):
        sha1 = hashlib.sha1(data).hexdigest()
        file_nodes.append(
            f'''   <mets:file CHECKSUM="{sha1}" CHECKSUMTYPE="SHA-1" GROUPID="FG0001" ID="FID{idx:04d}" MIMETYPE="image/tiff" SIZE="{len(data)}">
    <mets:FLocat LOCTYPE="URL" xlink:href="file://./{name}" xlink:type="simple"/>
   </mets:file>'''
        )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:mods="http://www.loc.gov/mods/v3" xmlns:xlink="http://www.w3.org/1999/xlink" LABEL="TEST PACKAGE" OBJID="test/objid" TYPE="ResCarta Monograph Metadata v3.1">
 <mets:metsHdr CREATEDATE="2020-01-01T00:00:00Z" RECORDSTATUS="COMPLETE">
  <mets:agent ROLE="CREATOR" TYPE="ORGANIZATION"><mets:name>ResCarta Tools</mets:name></mets:agent>
 </mets:metsHdr>
 <mets:dmdSec ID="DMD0001"><mets:mdWrap MDTYPE="MODS" MIMETYPE="text/xml"><mets:xmlData><mods:mods>
  <mods:titleInfo><mods:title>TEST PACKAGE</mods:title></mods:titleInfo>
  <mods:name><mods:namePart>HDL</mods:namePart></mods:name>
  <mods:typeOfResource>text</mods:typeOfResource>
  <mods:genre>book</mods:genre>
  <mods:originInfo><mods:dateCaptured encoding="iso8601">2020-01-01</mods:dateCaptured><mods:issuance>monographic</mods:issuance></mods:originInfo>
  <mods:language><mods:languageTerm authority="iso639-2b" type="code">eng</mods:languageTerm></mods:language>
  <mods:abstract>Test abstract</mods:abstract>
  <mods:identifier type="local">test/objid</mods:identifier>
  <mods:location><mods:url>test/objid</mods:url></mods:location>
  <mods:part order="1"><mods:extent unit="pages"><mods:start>1</mods:start><mods:end>{len(files)}</mods:end></mods:extent></mods:part>
 </mods:mods></mets:xmlData></mets:mdWrap></mets:dmdSec>
 <mets:fileSec><mets:fileGrp ID="FG0001">
{chr(10).join(file_nodes)}
 </mets:fileGrp></mets:fileSec>
</mets:mets>'''


def _write_zip(path: Path) -> None:
    files = [("00000001.tif", b"fake_tiff_1"), ("00000002.tif", b"fake_tiff_2")]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", _metadata_xml(files))
        for name, data in files:
            zf.writestr(name, data)


def _write_crosswalk(path: Path) -> None:
    payload = {
        "schema_version": "trace_net_dublin_core_crosswalk_refinement_v1",
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "dc": {"dc:identifier": "t_p_120_1176_p000001", "dc:type": ["technical_manual_page"]},
                "trace_net": {"trace_net:can_answer_directly": False, "trace_net:can_prove_claims": False},
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "dc": {"dc:identifier": "t_p_120_1176_p000002", "dc:type": ["technical_manual_page"]},
                "trace_net": {"trace_net:can_answer_directly": False, "trace_net:can_prove_claims": False},
            },
        ],
        "document_records": [
            {"document_id": "t_p_120_1176", "dc": {"dc:identifier": "t_p_120_1176"}, "trace_net": {}}
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_page_number_helpers() -> None:
    assert page_number_from_entry_name("00000013.tif") == 13
    assert page_number_from_entry_name("file://./00000509.tif") == 509
    assert page_number_from_page_id("t_p_120_1176_p000013") == 13


def test_parse_source_package_reads_mets_entries(tmp_path: Path) -> None:
    zpath = tmp_path / "metadata.zip"
    _write_zip(zpath)
    parsed = parse_source_package(zpath)
    assert parsed["package_summary"]["metadata_xml_present"] is True
    assert parsed["package_summary"]["zip_tiff_count"] == 2
    assert parsed["package_summary"]["checksum_mismatch_count"] == 0
    assert parsed["entries_by_page_number"]["1"]["entry_name"] == "00000001.tif"


def test_build_extension_enriches_pages(tmp_path: Path) -> None:
    zpath = tmp_path / "metadata.zip"
    cpath = tmp_path / "crosswalk.json"
    out = tmp_path / "out"
    _write_zip(zpath)
    _write_crosswalk(cpath)
    report = build_dublin_core_source_package_extension(
        dublin_core_refined_path=cpath,
        metadata_zip_path=zpath,
        output_dir=out,
        require_page_count=2,
        min_page_records=2,
        min_pages_with_source_package_entry=2,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["pages_with_source_package_entry_count"] == 2
    page = report["page_records"][0]
    assert page["source_package"]["trace_net:source_package_entry_name"] == "00000001.tif"
    assert page["source_package"]["trace_net:source_package_entry_checksum_match"] is True
    assert page["trace_net"]["can_answer_directly"] is False
    assert (out / "trace_net_dublin_core_source_package_pages_v1.jsonl").exists()
