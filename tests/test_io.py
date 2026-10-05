from anysection import Section, SectionProperty
from anysection.io import (
    read_json,
    read_properties_csv,
    write_json,
    write_properties_csv,
    write_wide_csv,
)


def make_section():
    section = Section(name="RHS 100x50x5", series="RHS", standard="EN 10210", source="test")
    section.add_property(
        SectionProperty(
            key="A",
            symbol="A",
            name="Sectional area",
            group="Sectional Area",
            value=13.7,
            unit="cm^2",
        )
    )
    section.add_property(
        SectionProperty(
            key="I_y",
            symbol="I_y",
            group="Bending",
            value=180.0,
            unit="cm^4",
        )
    )
    return section


def test_json_roundtrip(tmp_path):
    path = tmp_path / "sections.json"
    original = make_section()
    write_json(path, [original])
    loaded = read_json(path)
    assert len(loaded) == 1
    assert loaded[0].value("Iy") == 180.0


def test_properties_csv_roundtrip(tmp_path):
    path = tmp_path / "properties.csv"
    original = make_section()
    write_properties_csv(path, [original])
    loaded = read_properties_csv(path)
    assert len(loaded) == 1
    assert loaded[0].value("A") == 13.7
    assert loaded[0].value("Iy") == 180.0


def test_wide_export(tmp_path):
    path = tmp_path / "wide.csv"
    write_wide_csv(path, [make_section()])
    text = path.read_text(encoding="utf-8-sig")
    assert "A [cm^2]" in text
    assert "I_y [cm^4]" in text
