from anysection import Section, SectionProperty


def test_property_alias_lookup():
    section = Section(name="IPE 300", series="IPE", standard="EN 10365")
    section.add_property(
        SectionProperty(
            key="I_y",
            symbol="I_y",
            value=8356.0,
            unit="cm^4",
            group="Bending",
        )
    )
    section.add_property(
        SectionProperty(
            key="I_omega",
            symbol="I_ω",
            value=1.2,
            unit="cm^6",
            group="Warping",
        )
    )

    assert section.value("Iy") == 8356.0
    assert section.value("I_y") == 8356.0
    assert section.value("Iw") == 1.2
    assert section.value("missing") is None


def test_identifier_is_stable():
    a = Section(name="IPE 300", series="IPE", standard="EN 10365", source="Dlubal")
    b = Section(name="IPE 300", series="IPE", standard="EN 10365", source="Dlubal")
    assert a.identifier == b.identifier


def test_source_url_disambiguates_catalogue_entries():
    a = Section(
        name="UKA 100x75x8",
        series="Advance UKA",
        standard="BS EN 10056-1:1999",
        source="Dlubal",
        source_url="https://example.test/corus/uka-100x75x8",
    )
    b = Section(
        name="UKA 100x75x8",
        series="Advance UKA",
        standard="BS EN 10056-1:1999",
        source="Dlubal",
        source_url="https://example.test/tata/uka-100x75x8",
    )
    assert a.identifier != b.identifier
